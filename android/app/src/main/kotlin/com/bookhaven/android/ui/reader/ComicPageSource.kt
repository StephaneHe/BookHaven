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
 */
class ComicPageSource(
    context: Context,
    private val bookId: Int,
    private val api: ApiService,
    private val localCbz: File?,
    contentVersion: String,
    private val knownCount: Int? = null,
) {
    private val cacheDir = File(context.cacheDir, "comic_pages").apply { mkdirs() }
    private val imageExts = setOf("jpg", "jpeg", "png", "webp", "gif")
    private val ver = contentVersion.ifBlank { "0" }.replace(Regex("[^A-Za-z0-9]"), "_")
    private val prefix = "b${bookId}_v${ver}_"
    private val zipLock = Mutex()
    private var entryNames: List<String>? = null
    private var count = -1

    init { purgeOtherVersions() }

    /** Drop cached page files for THIS book whose content version differs (stale). */
    private fun purgeOtherVersions() {
        cacheDir.listFiles { f ->
            f.name.startsWith("b${bookId}_v") && !f.name.startsWith(prefix)
        }?.forEach { it.delete() }
    }

    suspend fun pageCount(): Int {
        if (count >= 0) return count
        count = when {
            knownCount != null -> knownCount
            localCbz != null -> withContext(Dispatchers.IO) {
                ZipFile(localCbz).use { z ->
                    entryNames = z.entries().asSequence()
                        .filter { !it.isDirectory && it.name.substringAfterLast('.', "").lowercase() in imageExts }
                        .map { it.name }.sorted().toList()
                    entryNames!!.size
                }
            }
            else -> api.getComicPages(bookId).pages.size
        }
        return count
    }

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
                val names = entryNames ?: run { pageCount(); entryNames!! }
                val name = names.getOrNull(index) ?: return@withContext null
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

    companion object { private const val MAX_CACHE_BYTES = 300L * 1024 * 1024 }
}
