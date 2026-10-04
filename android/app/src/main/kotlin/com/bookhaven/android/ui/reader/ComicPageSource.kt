package com.bookhaven.android.ui.reader

import android.content.Context
import com.bookhaven.android.data.api.ApiService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.File
import java.util.zip.ZipFile

/**
 * Natural page order ("p_2" before "p_10"), same as the server's
 * scanner.natural_key: digit runs compare numerically, the rest case-insensitively.
 * Offline order must match the server's or saved page numbers point elsewhere.
 */
internal object NaturalOrder : Comparator<String> {
    private val TOKEN = Regex("\\d+|\\D+")

    override fun compare(a: String, b: String): Int {
        val ta = TOKEN.findAll(a).map { it.value }.toList()
        val tb = TOKEN.findAll(b).map { it.value }.toList()
        for (i in 0 until minOf(ta.size, tb.size)) {
            val x = ta[i]; val y = tb[i]
            val c = if (x[0].isDigit() && y[0].isDigit()) {
                val nx = x.trimStart('0'); val ny = y.trimStart('0')
                if (nx.length != ny.length) nx.length - ny.length else nx.compareTo(ny)
            } else {
                x.lowercase().compareTo(y.lowercase())
            }
            if (c != 0) return c
        }
        return ta.size - tb.size
    }
}

/**
 * Serves comic pages ONE AT A TIME as cached Files — never the whole archive in
 * RAM (that was the OOM crash). Online: GET /api/books/<id>/comic-page/<n>.
 * Offline: read a single entry from the local CBZ with ZipFile (random access via
 * the central directory, not a full ZipInputStream sweep from the start).
 *
 * Cache invalidation: cached page files are keyed by BOTH book id and the server
 * content fingerprint ([contentVersion] = file_size:modified_at). When the server
 * regenerates a comic (e.g. a manhua rebuilt with more pages) the version changes,
 * so old files no longer match and are purged on construction — the reader never
 * serves stale pages. Files live in a bounded LRU disk cache under cacheDir/comic_pages.
 *
 * pageNames() exposes the ordered plate names (arcnames like NNNNN_NNN.ext) so the
 * reader can derive chapters exactly like the web (5-digit prefix / 10 = chapter).
 */
class ComicPageSource(
    context: Context,
    private val bookId: Int,
    private val api: ApiService,
    private val localCbz: File?,
    contentVersion: String,
    private val knownNames: List<String>? = null,
) {
    private val cacheDir = File(context.cacheDir, "comic_pages").apply { mkdirs() }
    private val imageExts = setOf("jpg", "jpeg", "png", "webp", "gif")
    private val ver = contentVersion.ifBlank { "0" }.replace(Regex("[^A-Za-z0-9]"), "_")
    private val prefix = "b${bookId}_v${ver}_"
    private val zipLock = Mutex()
    private var names: List<String>? = null

    init { purgeOtherVersions() }

    /** Drop cached page files for THIS book whose content version differs (stale). */
    private fun purgeOtherVersions() {
        cacheDir.listFiles { f ->
            f.name.startsWith("b${bookId}_v") && !f.name.startsWith(prefix)
        }?.forEach { it.delete() }
    }

    /** Ordered plate names (arcnames). Online: from the API; offline: CBZ entries. */
    suspend fun pageNames(): List<String> {
        names?.let { return it }
        names = when {
            knownNames != null -> knownNames
            localCbz != null -> withContext(Dispatchers.IO) {
                ZipFile(localCbz).use { z ->
                    z.entries().asSequence()
                        .filter { !it.isDirectory && it.name.substringAfterLast('.', "").lowercase() in imageExts }
                        .map { it.name }.sortedWith(NaturalOrder).toList()
                }
            }
            else -> api.getComicPages(bookId).pages
        }
        return names!!
    }

    suspend fun pageCount(): Int = pageNames().size

    /** A cached File for page [index] (fetched or extracted on demand). Null on failure. */
    suspend fun pageFile(index: Int): File? = withContext(Dispatchers.IO) {
        val dest = File(cacheDir, "${prefix}p${index}.img")
        if (dest.exists() && dest.length() > 0) {
            dest.setLastModified(System.currentTimeMillis())   // LRU touch
            return@withContext dest
        }
        try {
            val tmp = File(cacheDir, "${prefix}p${index}.part")
            if (localCbz != null) {
                val name = pageNames().getOrNull(index) ?: return@withContext null
                zipLock.withLock {
                    ZipFile(localCbz).use { z ->
                        z.getInputStream(z.getEntry(name)).use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
                    }
                }
            } else {
                api.getComicPage(bookId, index).byteStream().use { i -> tmp.outputStream().use { o -> i.copyTo(o) } }
            }
            if (!tmp.renameTo(dest)) { tmp.copyTo(dest, overwrite = true); tmp.delete() }
            trimCache()
            dest
        } catch (e: Exception) {
            null
        }
    }

    private fun trimCache() {
        val files = cacheDir.listFiles { f -> f.name.endsWith(".img") }?.toList() ?: return
        var total = files.sumOf { it.length() }
        if (total <= MAX_CACHE_BYTES) return
        for (f in files.sortedBy { it.lastModified() }) {
            if (total <= MAX_CACHE_BYTES) break
            total -= f.length(); f.delete()
        }
    }

    // 500 MB LRU: comfortably holds ~1 chapter prefetched ahead + recently-read plates
    // for the heaviest manhua (tall stitched strips), while staying bounded.
    companion object { private const val MAX_CACHE_BYTES = 500L * 1024 * 1024 }
}
