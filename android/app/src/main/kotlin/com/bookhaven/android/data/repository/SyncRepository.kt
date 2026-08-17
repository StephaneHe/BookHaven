package com.bookhaven.android.data.repository

import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.api.model.ProgressRequest
import com.bookhaven.android.data.db.dao.ReadingProgressDao
import com.bookhaven.android.data.db.entity.ReadingProgress
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SyncRepository @Inject constructor(
    private val api: ApiService,
    private val progressDao: ReadingProgressDao
) {
    /** Reconcile local and server reading progress. Highest progress (0–100) always wins. */
    suspend fun syncAll() {
        // 1. Push any writes that failed to reach the server earlier.
        progressDao.getPending().forEach { local ->
            val ok = runCatching {
                api.setProgress(local.bookId, ProgressRequest(local.progress, local.position))
            }.isSuccess
            if (ok) progressDao.upsert(local.copy(pendingSync = false))
        }

        // 2. Reconcile every book we know about locally.
        progressDao.getAll().forEach { local ->
            runCatching { api.getProgress(local.bookId) }.getOrNull()?.let { server ->
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
                        }
                        progressDao.upsert(local.copy(pendingSync = false))
                    }
                    else -> Unit   // equal: nothing to do
                }
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
