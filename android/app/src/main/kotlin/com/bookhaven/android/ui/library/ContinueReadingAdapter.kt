package com.bookhaven.android.ui.library

import android.content.SharedPreferences
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.bookhaven.android.R
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.databinding.ItemContinueReadingBinding

class ContinueReadingAdapter(
    private val serverUrl: () -> String,
    private val onClick: (Book) -> Unit,
    private val onRemove: (Book) -> Unit,
    private val onLongClick: (Book) -> Unit
) : ListAdapter<Book, ContinueReadingAdapter.VH>(DIFF) {

    inner class VH(val b: ItemContinueReadingBinding) : RecyclerView.ViewHolder(b.root) {
        fun bind(book: Book) {
            b.tvTitle.text = book.title
            b.ivCover.load("${serverUrl()}/api/books/${book.id}/cover") {
                crossfade(true)
                placeholder(R.drawable.ic_book_placeholder)
                error(R.drawable.ic_book_placeholder)
            }
            b.progressBar.progress = book.progress.toInt()
            b.root.setOnClickListener { onClick(book) }
            b.root.setOnLongClickListener { onLongClick(book); true }
            b.btnRemove.setOnClickListener { onRemove(book) }
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
        VH(ItemContinueReadingBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun onBindViewHolder(h: VH, position: Int) = h.bind(getItem(position))

    companion object {
        val DIFF = object : DiffUtil.ItemCallback<Book>() {
            override fun areItemsTheSame(a: Book, b: Book) = a.id == b.id
            override fun areContentsTheSame(a: Book, b: Book) = a == b
        }
    }
}
