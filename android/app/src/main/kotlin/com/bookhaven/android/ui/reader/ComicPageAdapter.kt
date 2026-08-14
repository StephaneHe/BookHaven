package com.bookhaven.android.ui.reader

import android.graphics.BitmapFactory
import android.view.ViewGroup
import android.widget.ImageView
import androidx.recyclerview.widget.RecyclerView

class ComicPageAdapter(private val pages: List<ByteArray>) :
    RecyclerView.Adapter<ComicPageAdapter.VH>() {

    class VH(val iv: ImageView) : RecyclerView.ViewHolder(iv)

    override fun getItemCount() = pages.size

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val iv = ImageView(parent.context).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
            scaleType = ImageView.ScaleType.FIT_CENTER
            adjustViewBounds = true
        }
        return VH(iv)
    }

    override fun onBindViewHolder(h: VH, position: Int) {
        val data = pages[position]
        h.iv.setImageBitmap(BitmapFactory.decodeByteArray(data, 0, data.size))
    }
}
