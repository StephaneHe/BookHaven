package com.bookhaven.android.ui.reader

import android.graphics.BitmapFactory
import android.graphics.Color
import android.net.Uri
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.FrameLayout
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.davemorrissey.labs.subscaleview.ImageSource
import com.davemorrissey.labs.subscaleview.SubsamplingScaleImageView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Webtoon (continuous vertical) reader for ONE chapter, matching the web mobile
 * reader: each plate fills the WIDTH (width = area × zoom, height = width × plate
 * ratio) and plates stack in a single vertical scroll — NO left/right page-flip,
 * NO fit-height. A footer offers "Chapitre suivant" / "— Fin —".
 *
 * Memory (P0-B safety): plates render through SubsamplingScaleImageView, which
 * tiles/down-samples via BitmapRegionDecoder (keeps a tiny base layer + only the
 * visible high-res tiles), files load on demand from a bounded LRU cache, and
 * off-screen holders are recycled. Only the current chapter's plates are bound.
 */
class ContinuousComicAdapter(
    private val plateIndices: List<Int>,          // GLOBAL plate indices in this chapter
    private val scope: CoroutineScope,
    private val effectiveWidthPx: () -> Int,      // screen width × zoom
    private val isLastChapter: Boolean,
    private val onNextChapter: () -> Unit,
    private val loadPage: suspend (Int) -> File?, // global index -> cached File
) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

    private val typePlate = 0
    private val typeFooter = 1

    /** Global plate index for a plate item position (used to save reading position). */
    fun globalIndexAt(position: Int): Int? = plateIndices.getOrNull(position)

    class PlateVH(val ssiv: SubsamplingScaleImageView) : RecyclerView.ViewHolder(ssiv) {
        var job: Job? = null
    }

    class FooterVH(view: View) : RecyclerView.ViewHolder(view)

    override fun getItemCount() = plateIndices.size + 1   // +1 footer

    override fun getItemViewType(position: Int) =
        if (position < plateIndices.size) typePlate else typeFooter

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
        if (viewType == typeFooter) {
            val ctx = parent.context
            val container = FrameLayout(ctx).apply {
                layoutParams = RecyclerView.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
                )
                setBackgroundColor(Color.BLACK)
            }
            val view: View = if (!isLastChapter) {
                Button(ctx).apply {
                    text = "Chapitre suivant ›"
                    setOnClickListener { onNextChapter() }
                }
            } else {
                TextView(ctx).apply {
                    text = "— Fin —"
                    setTextColor(Color.parseColor("#888888"))
                    textSize = 14f
                }
            }
            container.addView(view, FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ).apply { gravity = Gravity.CENTER; topMargin = 36; bottomMargin = 96 })
            return FooterVH(container)
        }
        val ssiv = SubsamplingScaleImageView(parent.context).apply {
            layoutParams = RecyclerView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            )
            setMinimumScaleType(SubsamplingScaleImageView.SCALE_TYPE_CENTER_INSIDE)
            setPanEnabled(false)         // the RecyclerView scrolls; SSIV just draws fit-width
            setZoomEnabled(false)        // zoom is applied by re-measuring item width
            setMinimumTileDpi(120)       // bound tile memory on very tall strips
            setBackgroundColor(Color.BLACK)
        }
        return PlateVH(ssiv)
    }

    override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
        if (holder !is PlateVH) return
        val globalIdx = plateIndices[position]
        holder.job?.cancel()
        holder.ssiv.recycle()
        // Provisional height so layout is roughly right before the real dims arrive.
        val w0 = effectiveWidthPx().coerceAtLeast(1)
        setItemHeight(holder.ssiv, w0)
        holder.job = scope.launch {
            val file = loadPage(globalIdx) ?: return@launch
            val (pw, ph) = withContext(Dispatchers.IO) { decodeBounds(file) }
            val width = effectiveWidthPx().coerceAtLeast(1)
            val height = if (pw > 0) (width.toLong() * ph / pw).toInt().coerceAtLeast(1) else width
            setItemHeight(holder.ssiv, height)
            holder.ssiv.setImage(ImageSource.uri(Uri.fromFile(file)))
        }
    }

    override fun onViewRecycled(holder: RecyclerView.ViewHolder) {
        if (holder is PlateVH) {
            holder.job?.cancel(); holder.job = null
            holder.ssiv.recycle()
        }
    }

    private fun setItemHeight(v: View, height: Int) {
        val lp = v.layoutParams as RecyclerView.LayoutParams
        if (lp.height != height) { lp.height = height; v.layoutParams = lp }
    }

    private fun decodeBounds(file: File): Pair<Int, Int> {
        val o = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        BitmapFactory.decodeFile(file.absolutePath, o)
        return o.outWidth to o.outHeight
    }
}
