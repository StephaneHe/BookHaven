package com.bookhaven.android.data.repository

import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.api.model.ProgressRequest
import com.bookhaven.android.data.db.dao.ReadingProgressDao
import com.bookhaven.android.data.db.entity.ReadingProgress
import retrofit2.HttpException
import javax.inject.Inject
import javax.inject.Singleton

/** HTTP 404 from the server = the book no longer exists there. */
private fun Throwable.isBookGone(): Boolean =
    this is HttpException && code() == 404

@Singleton
class SyncRepository @Inject constructor(
    private val api: ApiService,
    private val progressDao: ReadingProgressDao
) {
    /** Reconcile local and server reading progress. Highest progress (0–100) wins.
     *  When the server reports a book is gone (404), the stale local row is purged
     *  instead of being retried forever — the retry loop pushing progress to
     *  deleted books is what triggered the server-side FK violation / DB lock. */
    suspend fun syncAll() {
        // 1. Push any writes that failed to reach the server earlier.
        progressDao.getPending().forEach { local ->
            runCatching {
                api.setProgress(local.bookId, ProgressRequest(local.progress, local.position))
            }.onSuccess {
                progressDao.upsert(local.copy(pendingSync = false))   // only clear pending on real success
            }.onFailure { e ->
                if (e.isBookGone()) progressDao.deleteById(local.bookId)
                // any other error: keep pendingSync = true and retry next time
            }
        }

        // 2. Reconcile every book we know about locally.
        progressDao.getAll().forEach { local ->
            runCatching { api.getProgress(local.bookId) }
                .onSuccess { server ->
                    when {
                        server.progress > local.progress ->
                            progressDao.upsert(ReadingProgress(
                                bookId = local.bookId,
                                position = server.currentLocation,
                                progress = server.progress,
                                updatedAt = System.currentTimeMillis(),
                                pendingSync = false
                            ))
                        local.progress > server.progress -> {
                            runCatching {
                                api.setProgress(local.bookId, ProgressRequest(local.progress, local.position))
                            }.onSuccess {
                                progressDao.upsert(local.copy(pendingSync = false))
                            }.onFailure { e ->
                                if (e.isBookGone()) progressDao.deleteById(local.bookId)
                                else progressDao.upsert(local.copy(pendingSync = true))  // retry later
                            }
                        }
                        else -> Unit   // equal: nothing to do
                    }
                }
                .onFailure { e ->
                    if (e.isBookGone()) progressDao.deleteById(local.bookId)
                }
        }

        // 3. Discover books read on the web / another device.
        runCatching { api.getContinueReading() }.getOrNull()?.forEach { book ->
            if (progressDao.getById(book.id) == null) {
                runCatching { api.getProgress(book.id) }.getOrNull()?.let { server ->
                    if (server.progress > 0f) {
                        progressDao.upsert(ReadingProgress(
                            bookId = book.id,
                            position = server.currentLocation,
                            progress = server.progress,
                            updatedAt = System.currentTimeMillis(),
                            pendingSync = false
                        ))
                    }
                }
            }
        }
    }
}
