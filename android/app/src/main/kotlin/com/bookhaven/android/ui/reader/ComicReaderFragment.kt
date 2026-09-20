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

    // ── Webtoon detection: first plate ratio h/w > 2 (same rule as the web) ──────
    private suspend fun detectWebtoon(): Boolean {
        val f = source.pageFile(0) ?: return false
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(f.absolutePath, o)
        return o.outWidth > 0 && o.outHeight.toFloat() / o.outWidth > 2f
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

        renderChapter(chapterOfPlate(startPlate), startPlate)
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

    private val prefetchedChapters = HashSet<Int>()

    private fun setupScrollTracking() {
        b.rvContinuous.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrolled(rv: RecyclerView, dx: Int, dy: Int) {
                val lm = rv.layoutManager as? LinearLayoutManager ?: return
                val pos = lm.findFirstVisibleItemPosition()
                val adapter = rv.adapter as? ContinuousComicAdapter ?: return
                val globalIdx = adapter.globalIndexAt(pos) ?: return
                updateIndicator(globalIdx)
                val pct = (globalIdx + 1).toFloat() / totalPages * 100f
                viewLifecycleOwner.lifecycleScope.launch {
                    downloadRepo.saveProgress(bookId, globalIdx.toString(), pct)
                }
                // Near the end of the chapter → warm the NEXT chapter's first plates
                // so the chapter transition is instant (bounded, files only).
                val chap = chapters.getOrNull(chapterIdx) ?: return
                val next = chapters.getOrNull(chapterIdx + 1) ?: return
                if (lm.findLastVisibleItemPosition() >= chap.idxs.size - 2 &&
                    prefetchedChapters.add(chapterIdx + 1)) {
                    next.idxs.take(2).forEach { gi ->
                        viewLifecycleOwner.lifecycleScope.launch { source.pageFile(gi) }
                    }
                }
            }
        })
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
