package com.bookhaven.android.data.repository

import android.content.Context
import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.data.api.model.ProgressRequest
import com.bookhaven.android.data.db.dao.CachedBookDao
import com.bookhaven.android.data.db.dao.DownloadedBookDao
import com.bookhaven.android.data.db.dao.ReadingProgressDao
import com.bookhaven.android.data.db.entity.CachedBook
import com.bookhaven.android.data.db.entity.DownloadedBook
import com.bookhaven.android.data.db.entity.ReadingProgress
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class DownloadRepository @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: ApiService,
    private val downloadedBookDao: DownloadedBookDao,
    private val readingProgressDao: ReadingProgressDao,
    private val cachedBookDao: CachedBookDao
) {
    val downloads: Flow<List<DownloadedBook>> = downloadedBookDao.observeAll()

    suspend fun isDownloaded(bookId: Int): Boolean =
        downloadedBookDao.getById(bookId) != null

    suspend fun downloadBook(book: Book): Result<DownloadedBook> = runCatching {
        withContext(Dispatchers.IO) {
            val dir = context.getExternalFilesDir("books") ?: context.filesDir
            val file = File(dir, "${book.id}.${book.format}")
            api.downloadBook(book.id).byteStream().use { input ->
                file.outputStream().use { output -> input.copyTo(output) }
            }
            val entity = DownloadedBook(
                bookId = book.id, title = book.title, author = book.author,
                format = book.format, localPath = file.absolutePath,
                downloadedAt = System.currentTimeMillis(), fileSize = file.length()
            )
            downloadedBookDao.insert(entity)
            entity
        }
    }

    suspend fun deleteDownload(bookId: Int) {
        val entity = downloadedBookDao.getById(bookId) ?: return
        File(entity.localPath).delete()
        downloadedBookDao.delete(entity)
    }

    suspend fun saveProgress(bookId: Int, position: String, progress: Float = 0f) {
        // Mirror the web client (index.html updateProgress): a book with a real reading
        // location is never stored below 1%. Otherwise opening a downloaded EPUB — which
        // epub.js renders from page 1, momentarily reporting 0% — would push progress=0 and
        // drop the book from "Continue Reading" (the server filters progress > 0).
        val effectiveProgress = if (progress <= 0f && position.isNotBlank()) 1f else progress
        // Persist locally first so progress is never lost, then try to push to the server.
        readingProgressDao.upsert(
            ReadingProgress(bookId, position, effectiveProgress, System.currentTimeMillis(), pendingSync = false)
        )
        val pushed = runCatching {
            api.setProgress(bookId, ProgressRequest(effectiveProgress, position))
        }.isSuccess
        if (!pushed) {
            // Offline / server error: mark for later reconciliation by SyncRepository.
            readingProgressDao.upsert(
                ReadingProgress(bookId, position, effectiveProgress, System.currentTimeMillis(), pendingSync = true)
            )
        }
    }

    suspend fun getProgress(bookId: Int): ReadingProgress? =
        readingProgressDao.getById(bookId)

    /**
     * Reading position to open a book AT, reconciling this device with the server.
     *
     * The local Room row alone is stale the moment the book is read on another
     * device (e.g. the web reader): opening here would jump to wherever THIS
     * device last was, not the newest position. So:
     *
     *  - unpushed local progress (`pendingSync`) wins — it isn't on the server yet;
     *  - otherwise the local row is already synced, which means the server holds
     *    at least what we last pushed and possibly a newer position from another
     *    device, so the server value wins. We mirror it back into Room so the
     *    reader and later reads stay consistent.
     *
     * Falls back to whatever local we have if the server is unreachable or has no
     * saved position (offline, or never read anywhere).
     */
    suspend fun resolveProgress(bookId: Int): ReadingProgress? {
        val local = readingProgressDao.getById(bookId)
        if (local?.pendingSync == true) return local

        val remote = runCatching { api.getProgress(bookId) }.getOrNull()
        val remoteLoc = remote?.currentLocation.orEmpty()
        if (remote != null && remoteLoc.isNotBlank() && remoteLoc != local?.position) {
            val merged = ReadingProgress(
                bookId = bookId,
                position = remoteLoc,
                progress = remote.progress,
                updatedAt = System.currentTimeMillis(),
                pendingSync = false,
            )
            readingProgressDao.upsert(merged)
            return merged
        }
        return local
    }

    suspend fun getDownload(bookId: Int): DownloadedBook? =
        downloadedBookDao.getById(bookId)

    /** Replace the offline library snapshot with the latest online result. */
    suspend fun cacheLibrary(books: List<Book>) = withContext(Dispatchers.IO) {
        cachedBookDao.clear()
        cachedBookDao.insertAll(books.map {
            CachedBook(id = it.id, title = it.title, author = it.author,
                format = it.format, category = it.category)
        })
    }

    /** Read the offline library snapshot (used when the network is unreachable). */
    suspend fun getCachedLibrary(): List<Book> = withContext(Dispatchers.IO) {
        cachedBookDao.getAll().map {
            Book(id = it.id, title = it.title, author = it.author,
                format = it.format, category = it.category)
        }
    }
}
