package com.bookhaven.android

import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.data.api.model.ProgressRequest
import com.bookhaven.android.data.api.model.ProgressResponse
import com.bookhaven.android.data.db.dao.CachedBookDao
import com.bookhaven.android.data.db.dao.DownloadedBookDao
import com.bookhaven.android.data.db.entity.ReadingProgress
import com.bookhaven.android.data.repository.DownloadRepository
import com.bookhaven.android.data.repository.SyncRepository
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder

class ProgressSyncTest {
    @get:Rule val tmp = TemporaryFolder()

    private fun downloadRepo(api: FakeApi, dao: FakeProgressDao) = DownloadRepository(
        cacheContext(tmp.newFolder()),
        api.api,
        proxyOf<DownloadedBookDao> { name, _ -> if (name == "observeAll") flowOf(emptyList<Any>()) else null },
        dao,
        proxyOf<CachedBookDao> { _, _ -> null },
    )

    private fun row(id: Int, pos: String, pct: Float, pending: Boolean) =
        ReadingProgress(id, pos, pct, updatedAt = 1L, pendingSync = pending)

    // ── R55: resolveProgress ──

    @Test fun R55_localPendingSyncWinsWithoutAskingServer() = runBlocking {
        val local = row(1, "2.5000", 30f, pending = true)
        val dao = FakeProgressDao(local)
        val api = FakeApi { ProgressResponse(80f, "9.0000") }
        assertSame(local, downloadRepo(api, dao).resolveProgress(1))
        assertTrue(api.callsTo("getProgress").isEmpty())
        assertTrue(dao.upserts.isEmpty())
    }

    @Test fun R55_serverPositionAdoptedAndMirroredLocally() = runBlocking {
        val dao = FakeProgressDao(row(1, "2.5000", 30f, pending = false))
        val api = FakeApi { c -> if (c.name == "getProgress") ProgressResponse(80f, "9.1234") else null }
        val r = downloadRepo(api, dao).resolveProgress(1)!!
        assertEquals("9.1234", r.position)
        assertEquals(80f, r.progress, 0f)
        assertFalse(r.pendingSync)
        assertEquals(r, dao.rows[1])                 // mirrored into the local DB
    }

    @Test fun R55_serverAdoptedWhenNoLocalRow() = runBlocking {
        val dao = FakeProgressDao()
        val api = FakeApi { ProgressResponse(12f, "epubcfi(/6/8)") }
        assertEquals("epubcfi(/6/8)", downloadRepo(api, dao).resolveProgress(5)!!.position)
        assertEquals("epubcfi(/6/8)", dao.rows[5]!!.position)
    }

    @Test fun R55_fallsBackToLocalWhenServerUnreachableOrEmpty() = runBlocking {
        val local = row(1, "4", 40f, pending = false)
        val offline = FakeApi { throw RuntimeException("offline") }
        assertSame(local, downloadRepo(offline, FakeProgressDao(local)).resolveProgress(1))

        val empty = FakeApi { ProgressResponse(0f, "") }
        val dao = FakeProgressDao(local)
        assertSame(local, downloadRepo(empty, dao).resolveProgress(1))
        assertTrue(dao.upserts.isEmpty())

        assertNull(downloadRepo(offline, FakeProgressDao()).resolveProgress(99))
    }

    // ── R56: sync purges local progress on HTTP 404 ──

    @Test fun R56_pendingPushGets404LocalRowPurged() = runBlocking {
        val dao = FakeProgressDao(row(1, "3", 30f, pending = true))
        val api = FakeApi { c -> if (c.name == "getContinueReading") emptyList<Book>() else throw http(404) }
        SyncRepository(api.api, dao).syncAll()
        assertNull(dao.rows[1])
    }

    @Test fun R56_reconcileGetProgress404Purges() = runBlocking {
        val dao = FakeProgressDao(row(2, "3", 30f, pending = false))
        val api = FakeApi { c -> if (c.name == "getContinueReading") emptyList<Book>() else throw http(404) }
        SyncRepository(api.api, dao).syncAll()
        assertNull(dao.rows[2])
    }

    @Test fun R56_otherErrorsKeepTheRow() = runBlocking {
        val dao = FakeProgressDao(row(1, "3", 30f, pending = true), row(2, "5", 50f, pending = false))
        val api = FakeApi { c -> if (c.name == "getContinueReading") emptyList<Book>() else throw http(500) }
        SyncRepository(api.api, dao).syncAll()
        assertTrue(dao.rows[1]!!.pendingSync)          // still queued for retry
        assertEquals("5", dao.rows[2]!!.position)
    }

    // ── R57: pendingSync cleared only after a successful push ──

    @Test fun R57_pendingClearedAfterSuccessfulPush() = runBlocking {
        val dao = FakeProgressDao(row(1, "3.5000", 30f, pending = true))
        val api = FakeApi { c ->
            when (c.name) {
                "getProgress" -> ProgressResponse(30f, "3.5000")
                "getContinueReading" -> emptyList<Book>()
                else -> null   // setProgress OK
            }
        }
        SyncRepository(api.api, dao).syncAll()
        val push = api.callsTo("setProgress").first()
        assertEquals(listOf(1, ProgressRequest(30f, "3.5000")), push.args)
        assertFalse(dao.rows[1]!!.pendingSync)
    }

    @Test fun R57_pendingKeptWhenPushFails() = runBlocking {
        val dao = FakeProgressDao(row(1, "3.5000", 30f, pending = true))
        val api = FakeApi { c ->
            when (c.name) {
                "setProgress" -> throw RuntimeException("offline")
                "getProgress" -> ProgressResponse(10f, "1")
                "getContinueReading" -> emptyList<Book>()
                else -> null
            }
        }
        SyncRepository(api.api, dao).syncAll()
        assertTrue(dao.rows[1]!!.pendingSync)
        assertTrue(dao.upserts.none { it.bookId == 1 && !it.pendingSync })
    }

    @Test fun R57_saveProgressMarksPendingOnlyWhenPushFails() = runBlocking {
        val okDao = FakeProgressDao()
        downloadRepo(FakeApi { null }, okDao).saveProgress(1, "2.0000", 20f)
        assertFalse(okDao.rows[1]!!.pendingSync)

        val koDao = FakeProgressDao()
        downloadRepo(FakeApi { throw RuntimeException("offline") }, koDao).saveProgress(1, "2.0000", 20f)
        assertTrue(koDao.rows[1]!!.pendingSync)
        assertEquals("2.0000", koDao.rows[1]!!.position)
    }
}
