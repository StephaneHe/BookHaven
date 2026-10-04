package com.bookhaven.android.ui.reader

import android.content.Context
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

    private data class Chapter(val key: String, val num: Double, val idxs: List<Int>)

    companion object {
        private const val ZOOM_MIN = 40
        private const val ZOOM_MAX = 400
        private const val ZOOM_STEP = 15
        private const val MAX_PREFETCH = 200   // safety cap on plates warmed ahead (files only)
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
                val serverVer = fresh?.contentVersion.orEmpty()
                if (fresh != null && serverVer.isNotBlank() && serverVer != stored) {
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
            val startPage = (downloadRepo.resolveProgress(bookId)?.position?.toIntOrNull() ?: 0)
                .coerceIn(0, totalPages - 1)

            // Manhua/webtoon (tall first plate) -> continuous vertical reader like the
            // web; normal comics keep the paged horizontal flip.
            val isWebtoon = withContext(Dispatchers.IO) { detectWebtoon() }
            if (isWebtoon) {
                setupContinuous(startPage)
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
    private suspend fun setupContinuous(startPlate: Int) {
        b.viewPager.visibility = View.GONE
        b.hScroll.visibility = View.VISIBLE
        b.llTopControls.visibility = View.VISIBLE

        chapters = buildChapters(source.pageNames())
        // Extra layout space below the viewport so RecyclerView binds (and SSIV starts
        // decoding) the NEXT plates ~2 screens ahead → the next plate is already
        // rendered when you reach it (real prefetch for a webtoon reader). Bounded to
        // ~2 screens so at most ~1 extra tall strip is live (SSIV tiling keeps it safe).
        b.rvContinuous.layoutManager = PrefetchLayoutManager(requireContext())
        b.rvContinuous.setItemViewCacheSize(4)   // keep a few decoded holders around

        // Per-book zoom (device-local UI preference, like the web's localStorage).
        zoomPct = prefs.getInt(zoomKey(), 100).coerceIn(ZOOM_MIN, ZOOM_MAX)
        b.tvZoom.text = "$zoomPct%"

        b.btnZoomIn.setOnClickListener { setZoom(zoomPct + ZOOM_STEP) }
        b.btnZoomOut.setOnClickListener { setZoom(zoomPct - ZOOM_STEP) }
        b.tvZoom.setOnClickListener { setZoom(100) }                 // tap label = reset (fit width)
        b.btnChapterPrev.setOnClickListener { renderChapter(chapterIdx - 1, null) }
        b.btnChapterNext.setOnClickListener { renderChapter(chapterIdx + 1, null) }
        b.tvChapter.setOnClickListener { showChapterPicker() }

        setupPinchZoom()
        setupScrollTracking()

        readAnchor = startPlate
        renderChapter(chapterOfPlate(startPlate), startPlate)
        startPrefetchLoop()      // warm up to one chapter ahead as the user reads
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

    private fun renderChapter(index: Int, scrollToPlate: Int?) {
        if (chapters.isEmpty()) return
        chapterIdx = index.coerceIn(0, chapters.size - 1)
        val chap = chapters[chapterIdx]
        val adapter = ContinuousComicAdapter(
            plateIndices = chap.idxs,
            scope = viewLifecycleOwner.lifecycleScope,
            effectiveWidthPx = ::effectiveWidthPx,
            isLastChapter = chapterIdx >= chapters.size - 1,
            onNextChapter = { renderChapter(chapterIdx + 1, null) },
            loadPage = { source.pageFile(it) },
        )
        b.rvContinuous.layoutParams = b.rvContinuous.layoutParams.apply { width = effectiveWidthPx() }
        b.rvContinuous.adapter = adapter
        val chapLabel = if (chap.num % 1.0 == 0.0) chap.num.toInt().toString() else chap.num.toString()
        b.tvChapter.text = "Ch. $chapLabel  (${chapterIdx + 1}/${chapters.size})"

        val target = scrollToPlate ?: chap.idxs.firstOrNull() ?: 0
        val posInChapter = chap.idxs.indexOf(target).coerceAtLeast(0)
        (b.rvContinuous.layoutManager as LinearLayoutManager)
            .scrollToPositionWithOffset(posInChapter, 0)
        updateIndicator(target)
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

    private fun updateIndicator(globalIdx: Int) {
        b.tvPageNum.text = "${globalIdx + 1} / $totalPages"
        b.comicProgressBar.progress = ((globalIdx + 1).toFloat() / totalPages * 100f).toInt()
    }

    @Volatile private var readAnchor = 0     // global index of the top-visible plate
    private var prefetchLoop: Job? = null

    private fun setupScrollTracking() {
        b.rvContinuous.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrolled(rv: RecyclerView, dx: Int, dy: Int) {
                val lm = rv.layoutManager as? LinearLayoutManager ?: return
                val pos = lm.findFirstVisibleItemPosition()
                val adapter = rv.adapter as? ContinuousComicAdapter ?: return
                val globalIdx = adapter.globalIndexAt(pos) ?: return
                readAnchor = globalIdx           // drives the prefetch loop
                updateIndicator(globalIdx)
                val pct = (globalIdx + 1).toFloat() / totalPages * 100f
                viewLifecycleOwner.lifecycleScope.launch {
                    downloadRepo.saveProgress(bookId, globalIdx.toString(), pct)
                }
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
        zoomPct = z.coerceIn(ZOOM_MIN, ZOOM_MAX)
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
