package com.bookhaven.android.ui.reader

import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.graphics.BitmapFactory
import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import androidx.viewpager2.widget.ViewPager2
import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.data.api.model.SeriesRef
import com.bookhaven.android.data.api.toUserMessage
import com.bookhaven.android.data.repository.DownloadRepository
import com.bookhaven.android.databinding.FragmentComicReaderBinding
import com.bookhaven.android.ui.common.showError
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import kotlin.math.roundToInt

private const val TAG = "ComicReaderFragment"

@AndroidEntryPoint
class ComicReaderFragment : Fragment() {

    private var _b: FragmentComicReaderBinding? = null
    private val b get() = _b!!

    @Inject lateinit var api: ApiService
    @Inject lateinit var downloadRepo: DownloadRepository
    @Inject lateinit var prefs: SharedPreferences

    private var bookId = -1
    private var serverUrl = ""
    private var localPath: String? = null
    private var loadError: String? = null

    // Continuous (webtoon) state
    private lateinit var source: ComicPageSource
    private var totalPages = 0
    private var chapters: List<Chapter> = emptyList()
    private var chapterIdx = 0
    private var zoomPct = 100
    private var detail: Book? = null              // server book detail (webtoon flag, series neighbours)
    // Exact position to restore once the target plate has its real height:
    // (item position in the chapter, fraction 0..1 into that plate).
    private var pendingRestore: Pair<Int, Float>? = null

    private data class Chapter(val key: String, val num: Double, val idxs: List<Int>)

    companion object {
        private const val MAX_PREFETCH = 200   // safety cap on plates warmed ahead (files only)
        const val PREF_PRECACHE = "precache_chapters"          // chapters pre-cached ahead (0..5)
        const val PREF_DOWNLOAD_AHEAD = "download_ahead"       // also download them for offline
        private const val WEBTOON_SAMPLE = 4   // plates sampled by detectWebtoon()

        /**
         * dims: (width, height) of the first plates, null = unreadable. Landscape
         * plates (credits, double spreads) are ignored; webtoon when a strict
         * majority of the remaining plates are tall strips (h/w > 2).
         */
        internal fun isWebtoon(dims: List<Pair<Int, Int>?>): Boolean {
            val portrait = dims.filterNotNull().filter { (w, h) -> w > 0 && h >= w }
            if (portrait.isEmpty()) return false
            val tall = portrait.count { (w, h) -> h.toFloat() / w > 2f }
            return tall * 2 > portrait.size
        }

        fun newInstance(bookId: Int, serverUrl: String, localPath: String?) =
            ComicReaderFragment().apply {
                arguments = Bundle().apply {
                    putInt("book_id", bookId)
                    putString("server_url", serverUrl)
                    putString("local_path", localPath)
                }
            }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        bookId = arguments?.getInt("book_id", -1) ?: -1
        serverUrl = arguments?.getString("server_url") ?: ""
        localPath = arguments?.getString("local_path")
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View = FragmentComicReaderBinding.inflate(inflater, container, false)
        .also { _b = it }.root

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        viewLifecycleOwner.lifecycleScope.launch {
            // Cache keyed by the server content fingerprint (see ComicPageSource) so a
            // rebuilt comic is never served stale; offline copies offer to update.
            var local = localPath?.let { File(it) }?.takeIf { it.exists() }
            var contentVersion = ""
            var names: List<String>? = null

            if (local != null) {
                val stored = downloadRepo.getDownload(bookId)?.contentVersion ?: ""
                contentVersion = stored
                val fresh = withContext(Dispatchers.IO) { runCatching { api.getBookDetail(bookId) }.getOrNull() }
                detail = fresh
                val serverVer = fresh?.contentVersion.orEmpty()
                if (fresh != null && ComicReaderLogic.isOfflineCopyStale(stored, serverVer)) {
                    if (confirmUpdate()) {
                        val redownloaded = withContext(Dispatchers.IO) {
                            downloadRepo.deleteDownload(bookId)
                            downloadRepo.downloadBook(fresh).getOrNull()
                        }
                        if (redownloaded != null) {
                            local = File(redownloaded.localPath).takeIf { it.exists() }
                            contentVersion = redownloaded.contentVersion
                        } else {
                            Toast.makeText(requireContext(), "Mise à jour échouée — version hors-ligne conservée", Toast.LENGTH_SHORT).show()
                        }
                    } else {
                        Toast.makeText(requireContext(), "Version hors-ligne (peut être périmée)", Toast.LENGTH_SHORT).show()
                    }
                }
            } else {
                val resp = withContext(Dispatchers.IO) { runCatching { api.getComicPages(bookId) }.getOrNull() }
                detail = withContext(Dispatchers.IO) { runCatching { api.getBookDetail(bookId) }.getOrNull() }
                contentVersion = resp?.contentVersion.orEmpty()
                names = resp?.pages
            }

            source = ComicPageSource(
                requireContext().applicationContext, bookId, api, local, contentVersion, names
            )

            totalPages = withContext(Dispatchers.IO) {
                runCatching { source.pageCount() }.getOrElse { e ->
                    Log.e(TAG, "pageCount failed for bookId=$bookId", e)
                    loadError = "Failed to read comic: ${e.toUserMessage()}"
                    0
                }
            }
            if (totalPages == 0) {
                requireContext().showError(loadError ?: "No pages found in this comic")
                return@launch
            }

            b.comicProgressBar.max = 100
            // A plate index (paged) or "plate.fraction" (webtoon scroll position, as the web).
            val (startPage, startFrac) =
                ComicReaderLogic.parsePosition(downloadRepo.resolveProgress(bookId)?.position, totalPages)

            // Manhua / manhwa / webtoon -> ONE continuous vertical scroll, no page notion.
            // The server flag (series/category) is authoritative so such a book never
            // falls back to the paged reader; detection covers unflagged/offline books.
            val isWebtoon = ComicReaderLogic.useContinuousReader(detail?.webtoon) {
                withContext(Dispatchers.IO) { detectWebtoon() }
            }
            if (isWebtoon) {
                setupContinuous(startPage, startFrac)
            } else {
                setupPaged(startPage)
            }
        }
    }

    // ── Webtoon detection: same rule as the web (comicIsWebtoonDims) ─────────────
    // Samples the first plates, not plate 0 alone: scanlated webtoon chapters open
    // with a landscape credits page, webtoon volumes with a portrait cover.
    private suspend fun detectWebtoon(): Boolean {
        val dims = (0 until minOf(WEBTOON_SAMPLE, totalPages)).map { i ->
            source.pageFile(i)?.let { f ->
                val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
                BitmapFactory.decodeFile(f.absolutePath, o)
                o.outWidth to o.outHeight
            }
        }
        return isWebtoon(dims)
    }

    // ── Paged mode (normal comics) ──────────────────────────────────────────────
    private fun setupPaged(startPage: Int) {
        b.viewPager.visibility = View.VISIBLE
        b.hScroll.visibility = View.GONE
        b.llTopControls.visibility = View.GONE
        b.viewPager.adapter = ComicPageAdapter(totalPages, viewLifecycleOwner.lifecycleScope) { source.pageFile(it) }
        b.tvPageNum.text = "1 / $totalPages"
        if (startPage in 1 until totalPages) b.viewPager.setCurrentItem(startPage, false)
        b.viewPager.registerOnPageChangeCallback(object : ViewPager2.OnPageChangeCallback() {
            override fun onPageSelected(position: Int) {
                // A page kept alive by ViewPager2 keeps its zoom/pan: coming back to it
                // could land mid-page or at its bottom. Always show it from its default
                // fit (whole page, top included), like the web reader.
                ((b.viewPager.getChildAt(0) as? RecyclerView)
                    ?.findViewHolderForAdapterPosition(position) as? ComicPageAdapter.VH)
                    ?.ssiv?.resetScaleAndCenter()
                val pct = (position + 1).toFloat() / totalPages * 100f
                b.tvPageNum.text = "${position + 1} / $totalPages"
                b.comicProgressBar.progress = pct.toInt()
                viewLifecycleOwner.lifecycleScope.launch {
                    downloadRepo.saveProgress(bookId, position.toString(), pct)
                }
            }
        })
    }

    // ── Continuous (webtoon) mode ───────────────────────────────────────────────
    private suspend fun setupContinuous(startPlate: Int, startFrac: Float = 0f) {
        b.viewPager.visibility = View.GONE
        b.hScroll.visibility = View.VISIBLE
        b.llTopControls.visibility = View.VISIBLE
        b.tvPageNum.visibility = View.GONE          // webtoon: no "page X / N"

        chapters = buildChapters(source.pageNames())
        // Extra layout space below the viewport so RecyclerView binds (and SSIV starts
        // decoding) the NEXT plates ~2 screens ahead → the next plate is already
        // rendered when you reach it (real prefetch for a webtoon reader). Bounded to
        // ~2 screens so at most ~1 extra tall strip is live (SSIV tiling keeps it safe).
        b.rvContinuous.layoutManager = PrefetchLayoutManager(requireContext())
        b.rvContinuous.setItemViewCacheSize(4)   // keep a few decoded holders around

        // Per-book zoom (device-local UI preference, like the web's localStorage).
        zoomPct = ComicReaderLogic.clampZoom(prefs.getInt(zoomKey(), 100))
        b.tvZoom.text = "$zoomPct%"

        b.btnZoomIn.setOnClickListener { setZoom(zoomPct + ComicReaderLogic.ZOOM_STEP) }
        b.btnZoomOut.setOnClickListener { setZoom(zoomPct - ComicReaderLogic.ZOOM_STEP) }
        b.tvZoom.setOnClickListener { setZoom(100) }                 // tap label = reset (fit width)
        b.btnChapterPrev.setOnClickListener { chapterStep(-1) }
        b.btnChapterNext.setOnClickListener { chapterStep(1) }
        b.tvChapter.setOnClickListener { showChapterPicker() }

        setupPinchZoom()
        setupScrollTracking()

        readAnchor = startPlate
        // Initial render restores the stored position: do not re-save it (a finished
        // book would drop from 100 % to the % of its last plate's top).
        renderChapter(chapterOfPlate(startPlate), startPlate, startFrac, save = false)
        startPrefetchLoop()      // warm up to one chapter ahead as the user reads
        startSeriesPrecache()    // and the next chapters (files) of the series
    }

    private fun buildChapters(pages: List<String>): List<Chapter> {
        val out = mutableListOf<Chapter>()
        var cur: MutableList<Int>? = null
        var curKey = ""
        pages.forEachIndexed { i, name ->
            val m = Regex("^(\\d+)_").find(name)
            val key = m?.groupValues?.get(1) ?: "__"
            if (cur == null || curKey != key) {
                val idxs = mutableListOf<Int>()
                val num = m?.groupValues?.get(1)?.toDoubleOrNull()?.div(10) ?: (out.size + 1).toDouble()
                out.add(Chapter(key, num, idxs))
                cur = idxs; curKey = key
            }
            cur!!.add(i)
        }
        return out
    }

    private fun chapterOfPlate(plate: Int): Int {
        chapters.forEachIndexed { i, c ->
            if (c.idxs.isNotEmpty() && plate >= c.idxs.first() && plate <= c.idxs.last()) return i
        }
        return 0
    }

    private fun effectiveWidthPx(): Int {
        val screen = resources.displayMetrics.widthPixels
        return (screen * zoomPct / 100).coerceAtLeast(1)
    }

    private fun renderChapter(index: Int, scrollToPlate: Int?, frac: Float = 0f, save: Boolean = true) {
        if (chapters.isEmpty()) return
        chapterIdx = index.coerceIn(0, chapters.size - 1)
        val chap = chapters[chapterIdx]
        val isLast = chapterIdx >= chapters.size - 1
        val next = detail?.seriesNext
        val lm = b.rvContinuous.layoutManager as LinearLayoutManager
        val adapter = ContinuousComicAdapter(
            plateIndices = chap.idxs,
            scope = viewLifecycleOwner.lifecycleScope,
            effectiveWidthPx = ::effectiveWidthPx,
            footerLabel = when {
                !isLast -> "Chapitre suivant ›"
                next != null -> "Suivant : ${next.title} ›"
                else -> null
            },
            onFooterClick = { chapterStep(1) },
            loadPage = { source.pageFile(it) },
            onPlateSized = { pos, height ->
                pendingRestore?.let { (p, f) ->
                    if (p == pos) {
                        lm.scrollToPositionWithOffset(p, -(f * height).toInt())
                        pendingRestore = null
                    }
                }
            },
        )
        b.rvContinuous.layoutParams = b.rvContinuous.layoutParams.apply { width = effectiveWidthPx() }
        b.rvContinuous.adapter = adapter
        val chapLabel = if (chap.num % 1.0 == 0.0) chap.num.toInt().toString() else chap.num.toString()
        // One chapter per file (scanlated webtoons, tomes): show the book title, the
        // ‹ › buttons then move through the series.
        b.tvChapter.text = if (chapters.size > 1) "Ch. $chapLabel  (${chapterIdx + 1}/${chapters.size})"
                           else detail?.title ?: "Ch. $chapLabel"

        val target = scrollToPlate?.takeIf { it in chap.idxs } ?: chap.idxs.firstOrNull() ?: 0
        val posInChapter = chap.idxs.indexOf(target).coerceAtLeast(0)
        val f = if (scrollToPlate == target) frac else 0f
        pendingRestore = if (f > 0f) posInChapter to f else null
        lm.scrollToPositionWithOffset(posInChapter, 0)
        if (save) saveScrollProgress(target, f, finished = false)
    }

    /** Previous/next chapter of this file, then previous/next book of the series. */
    private fun chapterStep(dir: Int) {
        when (val step = ComicReaderLogic.chapterStep(
            chapterIdx, dir, chapters.size, detail?.seriesPrev, detail?.seriesNext)) {
            is ComicReaderLogic.ChapterStep.InFile -> renderChapter(step.index, null)
            is ComicReaderLogic.ChapterStep.Series -> openSeriesBook(step.ref)
            ComicReaderLogic.ChapterStep.None -> Unit
        }
    }

    private fun openSeriesBook(ref: SeriesRef) {
        viewLifecycleOwner.lifecycleScope.launch {
            val local = withContext(Dispatchers.IO) { downloadRepo.getDownload(ref.id) }
            startActivity(Intent(requireContext(), ReaderActivity::class.java).apply {
                putExtra(ReaderActivity.EXTRA_BOOK_ID, ref.id)
                putExtra(ReaderActivity.EXTRA_FORMAT, ref.format)
                putExtra(ReaderActivity.EXTRA_TITLE, ref.title)
                local?.let { putExtra(ReaderActivity.EXTRA_LOCAL_PATH, it.localPath) }
            })
            requireActivity().finish()
        }
    }

    /** Webtoon progress = exact scroll position "plate.fraction" + %, 100 only at the end. */
    private fun saveScrollProgress(globalIdx: Int, frac: Float, finished: Boolean) {
        val pct = ComicReaderLogic.progressPercent(globalIdx, frac, totalPages, finished)
        b.comicProgressBar.progress = pct.toInt()
        val location = ComicReaderLogic.formatPosition(globalIdx, frac)
        viewLifecycleOwner.lifecycleScope.launch {
            downloadRepo.saveProgress(bookId, location, pct)
        }
    }

    private fun showChapterPicker() {
        if (chapters.isEmpty()) return
        val labels = chapters.map { c ->
            val n = if (c.num % 1.0 == 0.0) c.num.toInt().toString() else c.num.toString()
            "Ch. $n"
        }.toTypedArray()
        AlertDialog.Builder(requireContext())
            .setTitle("Aller au chapitre")
            .setItems(labels) { _, which -> renderChapter(which, null) }
            .show()
    }

    @Volatile private var readAnchor = 0     // global index of the top-visible plate
    private var prefetchLoop: Job? = null
    private var seriesPrecache: Job? = null

    /**
     * Multi-chapter pre-cache (same rules as the web): once the current chapter's
     * strips are in the disk cache, warm the next k chapter files of the series
     * (first strips of each first, then the rest) into the shared 500 MB LRU page
     * cache, so opening the next chapter reads from disk. Optionally (Settings)
     * also download them for offline reading, within space limits. Runs in the
     * reader's lifecycle scope: leaving the reader cancels it.
     */
    private fun startSeriesPrecache() {
        val k = ComicReaderLogic.precacheCount(prefs.getInt(PREF_PRECACHE, ComicReaderLogic.PRECACHE_DEFAULT))
        val upcoming = (detail?.seriesFollowing ?: emptyList())
            .filter { it.format == "cbz" || it.format == "cbr" }.take(k)
        if (upcoming.isEmpty()) return
        seriesPrecache?.cancel()
        val appCtx = requireContext().applicationContext   // never touch the Fragment from IO
        seriesPrecache = viewLifecycleOwner.lifecycleScope.launch(Dispatchers.IO) {
            // 1. Never compete with the chapter being read.
            chapters.getOrNull(chapterIdx)?.idxs?.forEach { if (!isActive) return@launch; source.pageFile(it) }
            // 2. Page lists of the upcoming chapters (online only).
            val sources = LinkedHashMap<Int, ComicPageSource>()
            val counts = ArrayList<Pair<Int, Int>>()
            val sizes = ArrayList<Long>()
            for (ref in upcoming) {
                if (!isActive) return@launch
                val resp = runCatching { api.getComicPages(ref.id) }.getOrNull() ?: continue
                sources[ref.id] = ComicPageSource(appCtx, ref.id, api,
                                                  null, resp.contentVersion, resp.pages)
                counts.add(ref.id to resp.pages.size)
                sizes.add(ref.fileSize)
            }
            // 3. Warm the page cache: first strips of every chapter, then the rest.
            for ((id, page) in ComicReaderLogic.precacheQueue(
                    counts, whole = ComicReaderLogic.wholeChapters(sizes))) {
                if (!isActive) return@launch
                sources[id]?.pageFile(page)
            }
            // 4. Optional offline download ahead.
            if (!prefs.getBoolean(PREF_DOWNLOAD_AHEAD, false)) return@launch
            for (ref in upcoming) {
                if (!isActive) return@launch
                val book = runCatching { api.getBookDetail(ref.id) }.getOrNull() ?: continue
                val free = (appCtx.getExternalFilesDir("books") ?: appCtx.filesDir).usableSpace
                if (ComicReaderLogic.shouldDownloadAhead(
                        enabled = true, alreadyDownloaded = downloadRepo.isDownloaded(ref.id),
                        bookBytes = book.fileSize, downloadedBytes = downloadRepo.downloadedBytes(),
                        freeBytes = free)) {
                    downloadRepo.downloadBook(book)
                }
            }
        }
    }

    private fun setupScrollTracking() {
        b.rvContinuous.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrollStateChanged(rv: RecyclerView, newState: Int) {
                if (newState == RecyclerView.SCROLL_STATE_DRAGGING) pendingRestore = null   // user took over
            }

            override fun onScrolled(rv: RecyclerView, dx: Int, dy: Int) {
                if (pendingRestore != null) return          // still placing the restored position
                if (dx == 0 && dy == 0) return              // layout pass / programmatic jump, not reading
                val lm = rv.layoutManager as? LinearLayoutManager ?: return
                val adapter = rv.adapter as? ContinuousComicAdapter ?: return
                val pos = lm.findFirstVisibleItemPosition()
                if (pos == RecyclerView.NO_POSITION) return
                val globalIdx = adapter.globalIndexAt(pos)
                    ?: adapter.globalIndexAt(adapter.itemCount - 2) ?: return   // footer: last plate
                val view = lm.findViewByPosition(pos)
                val frac = if (adapter.globalIndexAt(pos) == null || view == null || view.height <= 0) 0.9999f
                           else (-view.top.toFloat() / view.height).coerceIn(0f, 0.9999f)
                readAnchor = globalIdx           // drives the prefetch loop
                val finished = chapterIdx >= chapters.size - 1 && !rv.canScrollVertically(1)
                saveScrollProgress(globalIdx, frac, finished)
            }
        })
    }

    /**
     * Continuous, memory-safe "one chapter ahead" prefetch: repeatedly warm the LRU
     * DISK cache (files only — no bitmap decode) with the rest of the current chapter
     * plus the ENTIRE next chapter, ahead of the reading position. Sequential (no
     * request storm), skips already-cached files, and re-computes from the latest
     * position each sweep so it always stays ahead. Bounded by MAX_PREFETCH and the
     * 500 MB LRU cache; SSIV decode is handled separately by PrefetchLayoutManager.
     */
    private fun startPrefetchLoop() {
        prefetchLoop?.cancel()
        prefetchLoop = viewLifecycleOwner.lifecycleScope.launch(Dispatchers.IO) {
            while (isActive) {
                val anchor = readAnchor
                val ci = chapterOfPlate(anchor)
                val targets = ArrayList<Int>()
                chapters.getOrNull(ci)?.idxs?.filterTo(targets) { it > anchor }   // rest of current chapter
                chapters.getOrNull(ci + 1)?.idxs?.let { targets.addAll(it) }       // entire next chapter
                for (gi in targets.take(MAX_PREFETCH)) {
                    if (!isActive) break
                    if (kotlin.math.abs(readAnchor - anchor) > 3) break            // moved a lot → recompute
                    source.pageFile(gi)                                            // no-op if already cached
                }
                kotlinx.coroutines.delay(400)                                      // polite idle between sweeps
            }
        }
    }

    // Pinch-to-zoom: live visual scale during the gesture, baked into the real
    // plate width (crisp re-render) on release. Buttons remain the reliable path.
    private fun setupPinchZoom() {
        val rv = b.rvContinuous
        val detector = ScaleGestureDetector(requireContext(),
            object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
                var live = 1f
                override fun onScaleBegin(d: ScaleGestureDetector): Boolean { live = 1f; return true }
                override fun onScale(d: ScaleGestureDetector): Boolean {
                    live = (live * d.scaleFactor).coerceIn(0.3f, 4f)
                    rv.pivotX = d.focusX; rv.pivotY = d.focusY
                    rv.scaleX = live; rv.scaleY = live
                    return true
                }
                override fun onScaleEnd(d: ScaleGestureDetector) {
                    rv.scaleX = 1f; rv.scaleY = 1f
                    setZoom((zoomPct * live).roundToInt())
                }
            })
        rv.addOnItemTouchListener(object : RecyclerView.SimpleOnItemTouchListener() {
            override fun onInterceptTouchEvent(rv: RecyclerView, e: MotionEvent): Boolean {
                detector.onTouchEvent(e)
                return detector.isInProgress
            }
            override fun onTouchEvent(rv: RecyclerView, e: MotionEvent) { detector.onTouchEvent(e) }
        })
    }

    private fun setZoom(z: Int) {
        zoomPct = ComicReaderLogic.clampZoom(z)
        b.tvZoom.text = "$zoomPct%"
        prefs.edit().putInt(zoomKey(), zoomPct).apply()
        // Preserve the reading position across the re-measure.
        val lm = b.rvContinuous.layoutManager as? LinearLayoutManager
        val pos = lm?.findFirstVisibleItemPosition() ?: 0
        b.rvContinuous.layoutParams = b.rvContinuous.layoutParams.apply { width = effectiveWidthPx() }
        b.rvContinuous.adapter?.notifyDataSetChanged()
        if (pos >= 0) lm?.scrollToPositionWithOffset(pos, 0)
    }

    private fun zoomKey() = "bookhaven.zoom.comic.$bookId"

    /** Ask the user whether to refresh a stale offline copy. */
    private suspend fun confirmUpdate(): Boolean = suspendCancellableCoroutine { cont ->
        val dialog = AlertDialog.Builder(requireContext())
            .setTitle("Contenu mis à jour")
            .setMessage("Une nouvelle version de ce comic est disponible sur le serveur. Mettre à jour la copie hors-ligne ?")
            .setPositiveButton("Mettre à jour") { _, _ -> if (cont.isActive) cont.resumeWith(Result.success(true)) }
            .setNegativeButton("Plus tard") { _, _ -> if (cont.isActive) cont.resumeWith(Result.success(false)) }
            .setOnCancelListener { if (cont.isActive) cont.resumeWith(Result.success(false)) }
            .create()
        cont.invokeOnCancellation { dialog.dismiss() }
        dialog.show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}

/**
 * Lays out extra content below the viewport so upcoming plates are bound (and their
 * SubsamplingScaleImageView starts decoding) well before they scroll into view —
 * the real "prefetch" for a continuous webtoon reader. Bounded to ~2 screens below
 * (and ~1 above) so at most ~1 extra tall strip is live at once; combined with SSIV
 * tiling + LRU cache this stays memory-safe (no P0-B OOM regression).
 */
private class PrefetchLayoutManager(context: Context) : LinearLayoutManager(context) {
    override fun calculateExtraLayoutSpace(state: RecyclerView.State, extraLayoutSpace: IntArray) {
        val h = if (height > 0) height else 2000
        extraLayoutSpace[0] = h          // above (scroll-back)
        extraLayoutSpace[1] = h * 2      // below: pre-bind ~2 screens ahead
    }
}
