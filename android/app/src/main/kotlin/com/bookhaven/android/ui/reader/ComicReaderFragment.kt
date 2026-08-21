package com.bookhaven.android.ui.reader

import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.viewpager2.widget.ViewPager2
import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.api.toUserMessage
import com.bookhaven.android.data.repository.DownloadRepository
import com.bookhaven.android.databinding.FragmentComicReaderBinding
import com.bookhaven.android.ui.common.showError
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.util.zip.ZipInputStream
import javax.inject.Inject

private const val TAG = "ComicReaderFragment"

@AndroidEntryPoint
class ComicReaderFragment : Fragment() {

    private var _b: FragmentComicReaderBinding? = null
    private val b get() = _b!!

    @Inject lateinit var api: ApiService
    @Inject lateinit var downloadRepo: DownloadRepository

    private var bookId = -1
    private var serverUrl = ""
    private var localPath: String? = null
    private var loadError: String? = null

    companion object {
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
            val pages = withContext(Dispatchers.IO) { loadPages() }
            if (pages.isEmpty()) {
                val msg = loadError ?: "No pages found in this comic"
                Log.e(TAG, "No pages loaded for bookId=$bookId: $msg")
                requireContext().showError(msg)
                return@launch
            }

            b.viewPager.adapter = ComicPageAdapter(pages)
            b.tvPageNum.text = "1 / ${pages.size}"
            b.comicProgressBar.max = 100

            // Restore saved position, reconciled with the server (see resolveProgress).
            val saved = downloadRepo.resolveProgress(bookId)
            val startPage = saved?.position?.toIntOrNull() ?: 0
            if (startPage > 0) b.viewPager.setCurrentItem(startPage, false)

            b.viewPager.registerOnPageChangeCallback(object : ViewPager2.OnPageChangeCallback() {
                override fun onPageSelected(position: Int) {
                    val total = pages.size
                    val pct = (position + 1).toFloat() / total * 100f
                    b.tvPageNum.text = "${position + 1} / $total"
                    b.comicProgressBar.progress = pct.toInt()
                    viewLifecycleOwner.lifecycleScope.launch {
                        downloadRepo.saveProgress(bookId, position.toString(), pct)
                    }
                }
            })
        }
    }

    private suspend fun loadPages(): List<ByteArray> = withContext(Dispatchers.IO) {
        val file = localPath?.let { File(it) } ?: run {
            try {
                val tmp = File(requireContext().cacheDir, "comic_$bookId.cbz")
                api.downloadBook(bookId).byteStream().use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
                tmp
            } catch (e: Exception) {
                Log.e(TAG, "Download failed for bookId=$bookId", e)
                loadError = "Download failed: ${e.toUserMessage()}"
                return@withContext emptyList()
            }
        }
        val imageExts = setOf("jpg", "jpeg", "png", "webp", "gif")
        val pages = mutableListOf<Pair<String, ByteArray>>()
        try {
            ZipInputStream(file.inputStream()).use { zip ->
                var entry = zip.nextEntry
                while (entry != null) {
                    val ext = entry.name.substringAfterLast('.', "").lowercase()
                    if (!entry.isDirectory && ext in imageExts) pages.add(entry.name to zip.readBytes())
                    entry = zip.nextEntry
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to extract pages for bookId=$bookId", e)
            loadError = "Failed to read comic: ${e.message ?: "unknown error"}"
        }
        pages.sortedBy { it.first }.map { it.second }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
