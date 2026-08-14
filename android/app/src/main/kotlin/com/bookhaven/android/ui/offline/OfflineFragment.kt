package com.bookhaven.android.ui.offline

import android.content.Intent
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.bookhaven.android.data.db.entity.DownloadedBook
import com.bookhaven.android.databinding.FragmentOfflineBinding
import com.bookhaven.android.databinding.ItemOfflineBookBinding
import com.bookhaven.android.ui.reader.ReaderActivity
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch

@AndroidEntryPoint
class OfflineFragment : Fragment() {

    private var _b: FragmentOfflineBinding? = null
    private val b get() = _b!!
    private val vm: OfflineViewModel by viewModels()

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View = FragmentOfflineBinding.inflate(inflater, container, false)
        .also { _b = it }.root

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val adapter = OfflineAdapter(::open, ::confirmDelete)
        b.rvOffline.layoutManager = LinearLayoutManager(requireContext())
        b.rvOffline.adapter = adapter
        viewLifecycleOwner.lifecycleScope.launch {
            vm.downloads.collect { list ->
                adapter.submitList(list)
                b.tvEmpty.visibility = if (list.isEmpty()) View.VISIBLE else View.GONE
            }
        }
    }

    private fun open(book: DownloadedBook) {
        startActivity(Intent(requireContext(), ReaderActivity::class.java).apply {
            putExtra(ReaderActivity.EXTRA_BOOK_ID, book.bookId)
            putExtra(ReaderActivity.EXTRA_FORMAT, book.format)
            putExtra(ReaderActivity.EXTRA_TITLE, book.title)
            putExtra(ReaderActivity.EXTRA_LOCAL_PATH, book.localPath)
        })
    }

    private fun confirmDelete(book: DownloadedBook) {
        AlertDialog.Builder(requireContext())
            .setTitle("Delete offline copy")
            .setMessage("Remove \"${book.title}\" from device?")
            .setPositiveButton("Delete") { _, _ -> vm.delete(book) }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}

class OfflineAdapter(
    private val onClick: (DownloadedBook) -> Unit,
    private val onDelete: (DownloadedBook) -> Unit
) : ListAdapter<DownloadedBook, OfflineAdapter.VH>(DIFF) {

    inner class VH(val b: ItemOfflineBookBinding) : RecyclerView.ViewHolder(b.root) {
        fun bind(book: DownloadedBook) {
            b.tvTitle.text = book.title
            b.tvSub.text = "${book.author} · ${book.format.uppercase()} · ${book.fileSize / 1024}KB"
            b.root.setOnClickListener { onClick(book) }
            b.root.setOnLongClickListener { onDelete(book); true }
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH =
        VH(ItemOfflineBookBinding.inflate(LayoutInflater.from(parent.context), parent, false))

    override fun onBindViewHolder(h: VH, position: Int) = h.bind(getItem(position))

    companion object {
        val DIFF = object : DiffUtil.ItemCallback<DownloadedBook>() {
            override fun areItemsTheSame(a: DownloadedBook, b: DownloadedBook) = a.bookId == b.bookId
            override fun areContentsTheSame(a: DownloadedBook, b: DownloadedBook) = a == b
        }
    }
}
