package com.bookhaven.android.ui.library

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.view.isVisible
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.bookhaven.android.R
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.databinding.ItemBookBinding

class BookAdapter(
    private val serverUrl: () -> String,
    private val downloads: () -> Set<Int>,
    private val downloading: () -> Set<Int>,
    private val onClick: (Book) -> Unit,
    private val onLongClick: (Book) -> Unit,
    private val onDownloadClick: (Book) -> Unit
) : ListAdapter<Book, BookAdapter.VH>(DIFF) {

    inner class VH(val b: ItemBookBinding) : RecyclerView.ViewHolder(b.root) {
        fun bind(book: Book) {
            b.tvTitle.text = book.title
            b.tvAuthor.text = book.author
            val url = "${serverUrl()}/api/books/${book.id}/cover"
            b.ivCover.load(url) {
                crossfade(true)
                placeholder(R.drawable.ic_book_placeholder)
                error(R.drawable.ic_book_placeholder)
            }
            val isDownloaded = downloads().contains(book.id)
            val isDownloading = downloading().contains(book.id)
            b.ivDownloaded.isVisible = isDownloaded
            b.pbDownloading.isVisible = isDownloading
            // Download action icon only when there's nothing downloaded/in-flight yet.
            b.ivDownload.isVisible = !isDownloaded && !isDownloading
            b.ivDownload.setOnClickListener { onDownloadClick(book) }
            b.root.setOnClickListener { onClick(book) }
            b.root.setOnLongClickListener { onLongClick(book); true }
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
        VH(ItemBookBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun onBindViewHolder(holder: VH, position: Int) = holder.bind(getItem(position))

    companion object {
        val DIFF = object : DiffUtil.ItemCallback<Book>() {
            override fun areItemsTheSame(a: Book, b: Book) = a.id == b.id
            override fun areContentsTheSame(a: Book, b: Book) = a == b
        }
    }
}
