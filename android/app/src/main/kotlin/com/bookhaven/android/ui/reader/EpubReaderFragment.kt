package com.bookhaven.android.ui.reader

import android.annotation.SuppressLint
import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebViewClient
import android.widget.SeekBar
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.repository.DownloadRepository
import com.bookhaven.android.databinding.FragmentEpubReaderBinding
import com.bookhaven.android.ui.common.showError
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import kotlin.math.roundToInt

@AndroidEntryPoint
class EpubReaderFragment : Fragment() {

    private var _b: FragmentEpubReaderBinding? = null
    private val b get() = _b!!

    @Inject lateinit var downloadRepo: DownloadRepository
    @Inject lateinit var api: ApiService

    private var bookId = -1
    private var serverUrl = ""
    private var localPath: String? = null

    @Volatile private var lastCfi = ""
    @Volatile private var lastProgress = 0f

    // True while the user is dragging the SeekBar, so page-change events don't fight the thumb.
    @Volatile private var isSeeking = false

    // Page position within epub.js's generated locations (for the SeekBar bubble label).
    @Volatile private var currentPage = 0
    @Volatile private var totalPages = 0

    companion object {
        fun newInstance(bookId: Int, serverUrl: String, localPath: String?) =
            EpubReaderFragment().apply {
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

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View = FragmentEpubReaderBinding.inflate(inflater, container, false)
        .also { _b = it }.root

    @SuppressLint("SetJavaScriptEnabled")
    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        with(b.webView.settings) {
            javaScriptEnabled = true
            allowFileAccess = true
            @Suppress("DEPRECATION") allowUniversalAccessFromFileURLs = true
            @Suppress("DEPRECATION") allowFileAccessFromFileURLs = true
            domStorageEnabled = true
            mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW
        }
        b.webView.webViewClient = WebViewClient()
        b.webView.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(msg: ConsoleMessage): Boolean {
                Log.d("EpubJS", "[${msg.messageLevel()}] ${msg.message()} (${msg.sourceId()}:${msg.lineNumber()})")
                return true
            }
        }
        b.webView.addJavascriptInterface(WebBridge(), "Android")
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(b.webView, true)

        viewLifecycleOwner.lifecycleScope.launch {
            // Restore reading position
            downloadRepo.getProgress(bookId)?.let { saved ->
                if (saved.position.isNotEmpty()) {
                    lastCfi = saved.position
                    lastProgress = saved.progress
                    _b?.epubSeekBar?.progress = saved.progress.toInt()
                }
            }

            // The WebView XHR sandbox drops the connection mid-body when fetching large
            // binaries over http://. Pre-fetch via OkHttp (which works) into a temp file,
            // then load epub.js from file:// — no XHR to the server needed.
            val epubPath = localPath
                ?: downloadRepo.getDownload(bookId)?.localPath?.let { if (File(it).exists()) it else null }
                ?: downloadToTemp()

            if (epubPath != null) {
                withContext(Dispatchers.Main) { loadReader(epubPath) }
            } else {
                withContext(Dispatchers.Main) { activity?.showError("Failed to load book") }
            }

            // Periodic progress save
            while (isActive) {
                delay(30_000L)
                if (lastCfi.isNotEmpty()) {
                    downloadRepo.saveProgress(bookId, lastCfi, lastProgress)
                }
            }
        }

        // Scrub to seek: show a page bubble while dragging, jump on release.
        b.epubSeekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar, progress: Int, fromUser: Boolean) {
                if (fromUser) {
                    if (totalPages > 0) currentPage = (progress / 100f * totalPages).roundToInt()
                    updateSeekLabel()
                }
            }
            override fun onStartTrackingTouch(sb: SeekBar) {
                isSeeking = true
                b.tvSeekLabel.visibility = View.VISIBLE
                updateSeekLabel()
            }
            override fun onStopTrackingTouch(sb: SeekBar) {
                isSeeking = false
                b.tvSeekLabel.visibility = View.GONE
                b.webView.evaluateJavascript("window.seekToProgress(${sb.progress});", null)
            }
        })
        // Disabled until epub.js has generated locations (can take 10-30s for long books).
        // Re-enabled by onLocationsReady() once generate() completes.
        b.epubSeekBar.isEnabled = false
        b.epubSeekBar.alpha = 0.5f
    }

    /** Position the page bubble above the SeekBar thumb and set its "current / total" text. */
    private fun updateSeekLabel() {
        val sb = _b?.epubSeekBar ?: return
        val label = _b?.tvSeekLabel ?: return
        label.text = "$currentPage / $totalPages"
        val ratio = if (sb.max > 0) sb.progress.toFloat() / sb.max else 0f
        val trackWidth = (sb.width - sb.paddingLeft - sb.paddingRight).coerceAtLeast(0)
        val thumbX = sb.paddingLeft + ratio * trackWidth
        label.translationX = (thumbX - label.width / 2f).coerceAtLeast(0f)
    }

    private suspend fun downloadToTemp(): String? = withContext(Dispatchers.IO) {
        val name = "epub_temp_$bookId.epub"
        val file = File(requireContext().cacheDir, name)
        if (file.exists() && file.length() > 0) return@withContext file.absolutePath
        val extFile = File(requireContext().externalCacheDir ?: file.parentFile, name)
        if (extFile.exists() && extFile.length() > 0) return@withContext extFile.absolutePath
        // Try up to 2 times. A partial download leaves a truncated zip that epub.js
        // can open (first chapter visible) but fails on generate() — always delete before retry.
        for (attempt in 1..2) {
            try {
                api.downloadBook(bookId).byteStream().use { input ->
                    file.outputStream().use { output -> input.copyTo(output) }
                }
                if (file.length() > 0) return@withContext file.absolutePath
            } catch (e: Exception) {
                Log.e("EpubReader", "temp download failed (attempt $attempt): $e")
            }
            file.delete()
        }
        null
    }

    private fun loadReader(epubPath: String) {
        val assets = requireContext().assets
        val jszip = assets.open("jszip.min.js").bufferedReader().use { it.readText() }
        val epubjs = assets.open("epub.min.js").bufferedReader().use { it.readText() }
        var html = assets.open("epub_reader.html").bufferedReader().use { it.readText() }

        val globals = "<script>" +
            "window.__BOOK_ID=$bookId;" +
            "window.__SERVER_URL=${jsString(serverUrl)};" +
            "window.__LOCAL_PATH=${jsString(epubPath)};" +
            "window.__SAVED_CFI=${jsString(lastCfi)};" +
            "</script>"
        html = html.replace("<head>", "<head>$globals")
        html = html.replace("<script src=\"jszip.min.js\"></script>", "<script>$jszip</script>")
        html = html.replace("<script src=\"epub.min.js\"></script>", "<script>$epubjs</script>")

        // Base URL "file:///android_asset/" gives the page a file:// origin so epub.js (via
        // JSZip) can XHR the local temp EPUB at file:///data/.../cache/… — a null base URL
        // yields an opaque about:blank origin that blocks file:// access even with
        // allowUniversalAccessFromFileURLs (that flag only applies to file://-origin pages).
        b.webView.loadDataWithBaseURL("file:///android_asset/", html, "text/html", "UTF-8", null)
    }

    private fun jsString(s: String): String =
        "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"

    inner class WebBridge {
        @JavascriptInterface
        fun onPageChange(cfi: String, progress: Float, pageNum: Int, total: Int) {
            lastCfi = cfi
            lastProgress = progress
            currentPage = pageNum
            totalPages = total
            activity?.runOnUiThread {
                // Don't fight the thumb while the user is dragging.
                if (!isSeeking) _b?.epubSeekBar?.progress = progress.toInt()
            }
        }

        @JavascriptInterface
        fun onLocationsReady(total: Int) {
            totalPages = total
            activity?.runOnUiThread {
                _b?.epubSeekBar?.isEnabled = true
                _b?.epubSeekBar?.alpha = 1f
            }
        }

        @JavascriptInterface
        fun onProgressCfi(cfi: String) {
            // Locations not ready yet — save CFI for recovery without touching the seek bar.
            if (cfi.isNotEmpty()) lastCfi = cfi
        }

        @JavascriptInterface
        fun onError(msg: String) {
            Log.e("EpubReader", "JS: $msg")
            activity?.runOnUiThread {
                activity?.showError("Cannot open book: $msg")
            }
        }
    }

    override fun onStop() {
        super.onStop()
        // Save on the Fragment's lifecycleScope (not viewLifecycleOwner, which is already
        // cancelled by onDestroyView) so the write actually runs when leaving the reader.
        if (lastCfi.isNotEmpty()) {
            lifecycleScope.launch {
                downloadRepo.saveProgress(bookId, lastCfi, lastProgress)
            }
        }
    }

    override fun onDestroyView() {
        b.webView.destroy()
        super.onDestroyView()
        _b = null
    }
}
