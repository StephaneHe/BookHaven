package com.bookhaven.android.ui.detail

import android.content.Intent
import android.content.SharedPreferences
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import coil.load
import com.bookhaven.android.R
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.databinding.FragmentBookDetailBinding
import com.bookhaven.android.di.DEFAULT_SERVER_URL
import com.bookhaven.android.ui.reader.ReaderActivity
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class BookDetailFragment : Fragment() {

    private var _b: FragmentBookDetailBinding? = null
    private val b get() = _b!!
    private val vm: BookDetailViewModel by viewModels()

    @Inject lateinit var prefs: SharedPreferences

    companion object {
        const val ARG_BOOK_ID = "book_id"
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View = FragmentBookDetailBinding.inflate(inflater, container, false).also { _b = it }.root

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val bookId = arguments?.getInt(ARG_BOOK_ID) ?: return
        vm.loadBook(bookId)

        viewLifecycleOwner.lifecycleScope.launch {
            vm.state.collect { state ->
                when (state) {
                    is DetailState.Loading -> {
                        b.progressBar.visibility = View.VISIBLE
                        b.scrollContent.visibility = View.GONE
                    }
                    is DetailState.Success -> {
                        b.progressBar.visibility = View.GONE
                        b.scrollContent.visibility = View.VISIBLE
                        bind(state.book)
                    }
                    is DetailState.Error -> {
                        b.progressBar.visibility = View.GONE
                        Toast.makeText(requireContext(), state.message, Toast.LENGTH_LONG).show()
                    }
                }
            }
        }

        viewLifecycleOwner.lifecycleScope.launch {
            vm.toast.collect { msg ->
                msg ?: return@collect
                Toast.makeText(requireContext(), msg, Toast.LENGTH_SHORT).show()
                vm.clearToast()
            }
        }
    }

    private fun bind(book: Book) {
        val serverUrl = prefs.getString("server_url", DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL
        b.ivCover.load("$serverUrl/api/books/${book.id}/cover") {
            crossfade(true)
            placeholder(R.drawable.ic_book_placeholder)
            error(R.drawable.ic_book_placeholder)
        }
        b.tvTitle.text = book.title
        b.tvAuthor.text = book.author.ifBlank { "Unknown author" }
        b.tvCategory.text = "Category: ${book.category.ifBlank { "—" }}"
        b.tvGenre.text = "Genre: ${book.genre.ifBlank { "—" }}"
        b.tvFormat.text = "Format: ${book.format.uppercase()}"
        b.tvFileSize.text = if (book.fileSize > 0) "Size: ${book.fileSize / 1024} KB" else ""
        b.tvSeries.text = if (book.series.isNotBlank())
            "Series: ${book.series}${if (book.seriesIndex > 0) " #${book.seriesIndex.toInt()}" else ""}"
        else ""
        b.tvSeries.visibility = if (book.series.isNotBlank()) View.VISIBLE else View.GONE

        if (book.progress > 0f) {
            b.readingProgressBar.visibility = View.VISIBLE
            b.tvProgressText.visibility = View.VISIBLE
            b.readingProgressBar.progress = book.progress.toInt()
            b.tvProgressText.text = "${book.progress.toInt()}% read"
            b.btnRemoveProgress.visibility = View.VISIBLE
        } else {
            b.readingProgressBar.visibility = View.GONE
            b.tvProgressText.visibility = View.GONE
            b.btnRemoveProgress.visibility = View.GONE
        }

        b.btnRead.setOnClickListener {
            startActivity(Intent(requireContext(), ReaderActivity::class.java).apply {
                putExtra(ReaderActivity.EXTRA_BOOK_ID, book.id)
                putExtra(ReaderActivity.EXTRA_FORMAT, book.format)
                putExtra(ReaderActivity.EXTRA_TITLE, book.title)
            })
        }
        b.btnDownload.setOnClickListener { vm.downloadBook(book) }
        b.btnRemoveProgress.setOnClickListener { vm.removeProgress(book.id) }
        b.btnShare.setOnClickListener {
            val url = "${serverUrl}/api/books/${book.id}"
            val intent = Intent(Intent.ACTION_SEND).apply {
                type = "text/plain"; putExtra(Intent.EXTRA_TEXT, url)
            }
            startActivity(Intent.createChooser(intent, "Share book link"))
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
