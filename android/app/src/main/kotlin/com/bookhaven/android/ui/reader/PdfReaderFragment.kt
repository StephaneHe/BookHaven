package com.bookhaven.android.ui.reader

import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.Bundle
import android.os.ParcelFileDescriptor
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.api.toUserMessage
import com.bookhaven.android.data.repository.DownloadRepository
import com.bookhaven.android.databinding.FragmentPdfReaderBinding
import com.bookhaven.android.ui.common.showError
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject

private const val TAG = "PdfReaderFragment"

@AndroidEntryPoint
class PdfReaderFragment : Fragment() {

    private var _b: FragmentPdfReaderBinding? = null
    private val b get() = _b!!

    @Inject lateinit var api: ApiService
    @Inject lateinit var downloadRepo: DownloadRepository

    private var bookId = -1
    private var serverUrl = ""
    private var localPath: String? = null
    private var renderer: PdfRenderer? = null
    private var tempFile: File? = null
    private var pageCount = 0
    private var resolveError: String? = null

    companion object {
        fun newInstance(bookId: Int, serverUrl: String, localPath: String?) =
            PdfReaderFragment().apply {
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
    ): View = FragmentPdfReaderBinding.inflate(inflater, container, false)
        .also { _b = it }.root

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        val lm = LinearLayoutManager(requireContext())
        b.rvPdf.layoutManager = lm

        b.rvPdf.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrollStateChanged(rv: RecyclerView, newState: Int) {
                if (newState == RecyclerView.SCROLL_STATE_IDLE && pageCount > 0) {
                    val page = lm.findFirstVisibleItemPosition().coerceAtLeast(0)
                    val pct = (page + 1).toFloat() / pageCount * 100f
                    b.tvPageInfo.text = "${page + 1} / $pageCount · ${pct.toInt()}%"
                    b.pdfProgressBar.progress = pct.toInt()
                    viewLifecycleOwner.lifecycleScope.launch {
                        downloadRepo.saveProgress(bookId, page.toString(), pct)
                    }
                }
            }
        })

        viewLifecycleOwner.lifecycleScope.launch {
            b.progressBar.visibility = View.VISIBLE
            val file = withContext(Dispatchers.IO) { resolveFile() }
            b.progressBar.visibility = View.GONE
            if (file == null) {
                val msg = resolveError ?: "Failed to open PDF"
                Log.e(TAG, "resolveFile() returned null for bookId=$bookId: $msg")
                requireContext().showError(msg)
                return@launch
            }
            val pfd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
            renderer = PdfRenderer(pfd)
            pageCount = renderer!!.pageCount
            b.tvPageInfo.text = "1 / $pageCount"
            b.pdfProgressBar.max = 100
            b.rvPdf.adapter = PdfPageAdapter(renderer!!, pageCount)

            // Restore saved position
            val saved = downloadRepo.getProgress(bookId)
            if (saved != null && saved.position.isNotEmpty()) {
                val page = saved.position.toIntOrNull() ?: 0
                if (page > 0) b.rvPdf.scrollToPosition(page)
            }
        }
    }

    private suspend fun resolveFile(): File? = withContext(Dispatchers.IO) {
        localPath?.let { return@withContext File(it) }
        try {
            val tmp = File(requireContext().cacheDir, "pdf_$bookId.pdf")
            api.downloadBook(bookId).byteStream().use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
            tempFile = tmp; tmp
        } catch (e: Exception) {
            Log.e(TAG, "Download failed for bookId=$bookId", e)
            resolveError = "Download failed: ${e.toUserMessage()}"
            null
        }
    }

    override fun onDestroyView() {
        renderer?.close()
        tempFile?.delete()
        super.onDestroyView()
        _b = null
    }
}

class PdfPageAdapter(
    private val renderer: PdfRenderer,
    private val count: Int
) : RecyclerView.Adapter<PdfPageAdapter.VH>() {

    class VH(val iv: ImageView) : RecyclerView.ViewHolder(iv)

    override fun getItemCount() = count

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val iv = ImageView(parent.context).apply {
            layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            adjustViewBounds = true
        }
        return VH(iv)
    }

    override fun onBindViewHolder(h: VH, position: Int) {
        val page = renderer.openPage(position)
        val width = h.iv.context.resources.displayMetrics.widthPixels
        val height = (width.toFloat() * page.height / page.width).toInt()
        val bmp = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
        page.close()
        h.iv.setImageBitmap(bmp)
    }
}
