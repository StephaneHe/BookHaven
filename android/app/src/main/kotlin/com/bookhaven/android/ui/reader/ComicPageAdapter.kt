package com.bookhaven.android.ui.reader

import android.net.Uri
import android.view.ViewGroup
import androidx.recyclerview.widget.RecyclerView
import com.davemorrissey.labs.subscaleview.ImageSource
import com.davemorrissey.labs.subscaleview.SubsamplingScaleImageView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.io.File

/**
 * One page per item, displayed by SubsamplingScaleImageView, which tiles and
 * down-samples large images (incl. 15 000 px webtoon strips) via
 * BitmapRegionDecoder — so no full-size bitmap is ever allocated. Pages are
 * loaded lazily as Files (bounded LRU cache) and recycled off-screen.
 */
class ComicPageAdapter(
    private val count: Int,
    private val scope: CoroutineScope,
    private val loadPage: suspend (Int) -> File?,
) : RecyclerView.Adapter<ComicPageAdapter.VH>() {

    class VH(val ssiv: SubsamplingScaleImageView) : RecyclerView.ViewHolder(ssiv) {
        var job: Job? = null
    }

    override fun getItemCount() = count

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val v = SubsamplingScaleImageView(parent.context).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            setMinimumScaleType(SubsamplingScaleImageView.SCALE_TYPE_CENTER_INSIDE)
        }
        return VH(v)
    }

    override fun onBindViewHolder(h: VH, position: Int) {
        h.job?.cancel()
        h.ssiv.recycle()
        h.job = scope.launch {
            val file = loadPage(position) ?: return@launch
            h.ssiv.setImage(ImageSource.uri(Uri.fromFile(file)))
        }
    }

    override fun onViewRecycled(h: VH) {
        h.job?.cancel()
        h.job = null
        h.ssiv.recycle()
    }
}
