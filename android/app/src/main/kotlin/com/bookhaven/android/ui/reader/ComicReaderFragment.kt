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
            // Read pages ON DEMAND: offline from the local CBZ (ZipFile random
            // access), online from the paged API. Never load the whole archive.
            val local = localPath?.let { File(it) }?.takeIf { it.exists() }
            val source = ComicPageSource(requireContext().applicationContext, bookId, api, local)

            val count = withContext(Dispatchers.IO) {
                runCatching { source.pageCount() }.getOrElse { e ->
                    Log.e(TAG, "pageCount failed for bookId=$bookId", e)
                    loadError = "Failed to read comic: ${e.toUserMessage()}"
                    0
                }
            }
            if (count == 0) {
                requireContext().showError(loadError ?: "No pages found in this comic")
                return@launch
            }

            b.viewPager.adapter = ComicPageAdapter(count, viewLifecycleOwner.lifecycleScope) { source.pageFile(it) }
            b.tvPageNum.text = "1 / $count"
            b.comicProgressBar.max = 100

            // Restore saved position, reconciled with the server (see resolveProgress).
            val saved = downloadRepo.resolveProgress(bookId)
            val startPage = saved?.position?.toIntOrNull() ?: 0
            if (startPage in 1 until count) b.viewPager.setCurrentItem(startPage, false)

            b.viewPager.registerOnPageChangeCallback(object : ViewPager2.OnPageChangeCallback() {
                override fun onPageSelected(position: Int) {
                    val pct = (position + 1).toFloat() / count * 100f
                    b.tvPageNum.text = "${position + 1} / $count"
                    b.comicProgressBar.progress = pct.toInt()
                    viewLifecycleOwner.lifecycleScope.launch {
                        downloadRepo.saveProgress(bookId, position.toString(), pct)
                    }
                }
            })
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
