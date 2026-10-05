package com.bookhaven.android

import android.content.ContextWrapper
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.data.db.dao.CachedBookDao
import com.bookhaven.android.data.db.dao.DownloadedBookDao
import com.bookhaven.android.data.repository.DownloadRepository
import com.bookhaven.android.ui.reader.ComicReaderLogic
import com.google.gson.Gson
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.runBlocking
import okhttp3.MediaType
import okhttp3.ResponseBody
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.BufferedSource
import okio.buffer
import okio.source
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.io.IOException
import java.io.InputStream

/** R98 (Android): pre-cache of the next chapters of a webtoon series. */
class ChapterPrecacheTest {
    @get:Rule val tmp = TemporaryFolder()

    @Test fun R98_queueFirstStripsOfEveryChapterThenTheRest() {
        val q = ComicReaderLogic.precacheQueue(listOf(10 to 4, 11 to 3, 12 to 1))
        assertEquals(listOf(10 to 0, 10 to 1, 11 to 0, 11 to 1, 12 to 0,     // first 2 strips of each
                            10 to 2, 10 to 3, 11 to 2), q)                   // then chapter by chapter
    }

    @Test fun R98_byteBudgetKeepsOnlyFirstStripsOfOversizedChapters() {
        val mb = 1024L * 1024
        val whole = ComicReaderLogic.wholeChapters(listOf(300 * mb, 300 * mb, 50 * mb), budget = 400 * mb)
        assertEquals(listOf(true, false, true), whole)            // next always; then within budget
        val q = ComicReaderLogic.precacheQueue(listOf(1 to 4, 2 to 4, 3 to 3), whole = whole)
        assertEquals(listOf(1 to 0, 1 to 1, 2 to 0, 2 to 1, 3 to 0, 3 to 1, 1 to 2, 1 to 3, 3 to 2), q)
    }

    @Test fun R103_folderPerChapterSeasonFile() {
        assertEquals("Chapter 48.00 Season 2 Start" to 48.0,
            ComicReaderLogic.chapterKey("Chapter 48.00 Season 2 Start/01.jpg"))
        assertEquals("01725" to 172.5, ComicReaderLogic.chapterKey("01725_003.jpg"))      // manhua plates
        assertEquals("__" to null, ComicReaderLogic.chapterKey("p_0.png"))                 // one-chapter file
        val names = listOf("Chapter 48.00 Season 2 Start/01.jpg", "Chapter 48.00 Season 2 Start/02.jpg",
                           "Chapter 49.00/01.jpg", "Chapter 49.00/02.jpg", "Chapter 49.00/03.jpg")
        assertEquals(2, ComicReaderLogic.firstChapterLength(names))
        assertEquals(3, ComicReaderLogic.firstChapterLength(listOf("p_0.png", "p_1.png", "p_2.png")))
    }

    @Test fun R103_oversizedNextFileIsNotTakenWhole() {
        val mb = 1024L * 1024
        // next = a 500 MB file (more than the 400 MB budget): first strips only
        assertEquals(listOf(false, true), ComicReaderLogic.wholeChapters(listOf(500 * mb, 50 * mb)))
    }

    @Test fun R98_neverBeyondKAndKClamped() {
        assertEquals(3, ComicReaderLogic.PRECACHE_DEFAULT)
        assertEquals(0, ComicReaderLogic.precacheCount(-2))       // off
        assertEquals(2, ComicReaderLogic.precacheCount(2))
        assertEquals(5, ComicReaderLogic.precacheCount(40))       // hard max
        assertTrue(ComicReaderLogic.precacheQueue(emptyList()).isEmpty())
    }

    @Test fun R98_bookDetailListsUpcomingChapters() {
        val b = Gson().fromJson(
            """{"id":1,"title":"Ch 1","series_following":[{"id":2,"title":"Ch 2","format":"cbz"},
               {"id":3,"title":"Ch 3","format":"cbz"}]}""", Book::class.java)
        assertEquals(listOf(2, 3), b.seriesFollowing?.map { it.id })
    }

    @Test fun R98_downloadAheadRespectsOptionAndSpaceLimits() {
        val mb = 1024L * 1024
        val ok = { downloaded: Long, free: Long, enabled: Boolean, already: Boolean ->
            ComicReaderLogic.shouldDownloadAhead(enabled, already, 80 * mb, downloaded, free)
        }
        assertTrue(ok(100 * mb, 5000 * mb, true, false))
        assertFalse(ok(100 * mb, 5000 * mb, false, false))                       // option off (default)
        assertFalse(ok(100 * mb, 5000 * mb, true, true))                         // already offline
        assertFalse(ok(2048 * mb - 10 * mb, 5000 * mb, true, false))             // 2 GB total cap
        assertFalse(ok(100 * mb, 550 * mb, true, false))                         // keeps 500 MB free
    }

    @Test fun R98_nextChapterServedFromThePrecacheWithoutNetwork() = runBlocking {
        val root = tmp.newFolder()
        // Pre-cache (reader of chapter N) downloads chapter N+1 = book 21, version V7.
        val online = FakeApi { c ->
            if (c.name == "getComicPage") "STRIP${c.args[1]}".toByteArray().toResponseBody() else null
        }
        val warm = com.bookhaven.android.ui.reader.ComicPageSource(
            cacheContext(root), 21, online.api, null, "V7", listOf("p0.jpg", "p1.jpg"))
        warm.pageFile(0); warm.pageFile(1)
        assertEquals(2, online.callsTo("getComicPage").size)
        // Opening chapter N+1 later: a NEW source of the same book/version reads the disk cache.
        val offline = FakeApi { error("network must not be used for a pre-cached page") }
        val next = com.bookhaven.android.ui.reader.ComicPageSource(
            cacheContext(root), 21, offline.api, null, "V7", listOf("p0.jpg", "p1.jpg"))
        assertEquals("STRIP0", next.pageFile(0)!!.readText())
        assertEquals("STRIP1", next.pageFile(1)!!.readText())
        assertTrue(offline.calls.isEmpty())
    }

    // ── downloads never leave a half file (cancelled / failed read-ahead) ──

    private fun repo(dir: File, body: () -> ResponseBody, inserts: MutableList<String>) = DownloadRepository(
        object : ContextWrapper(null) {
            override fun getExternalFilesDir(type: String?): File = dir
            override fun getFilesDir(): File = dir
            override fun getCacheDir(): File = dir
        },
        FakeApi { call -> if (call.name == "downloadBook") body() else null }.api,
        proxyOf<DownloadedBookDao> { name, _ ->
            when (name) { "observeAll" -> flowOf(emptyList<Any>()); "insert" -> { inserts += name; Unit }; else -> null }
        },
        FakeProgressDao(),
        proxyOf<CachedBookDao> { _, _ -> null },
    )

    @Test fun R98_completedDownloadIsRenamedFromPart() = runBlocking {
        val dir = tmp.newFolder(); val inserts = mutableListOf<String>()
        val r = repo(dir, { "CBZDATA".toByteArray().toResponseBody() }, inserts)
            .downloadBook(Book(id = 7, title = "Ch 7", format = "cbz"))
        assertTrue(r.isSuccess)
        assertEquals("CBZDATA", File(dir, "7.cbz").readText())
        assertFalse(File(dir, "7.cbz.part").exists())
        assertEquals(1, inserts.size)
    }

    @Test fun R98_interruptedDownloadLeavesNoFile() = runBlocking {
        val dir = tmp.newFolder(); val inserts = mutableListOf<String>()
        val broken = object : ResponseBody() {
            override fun contentType(): MediaType? = null
            override fun contentLength(): Long = -1
            override fun source(): BufferedSource = object : InputStream() {
                var n = 0
                override fun read(): Int { if (n++ > 100) throw IOException("connection lost"); return 1 }
            }.source().buffer()
        }
        val r = repo(dir, { broken }, inserts).downloadBook(Book(id = 8, title = "Ch 8", format = "cbz"))
        assertTrue(r.isFailure)
        assertFalse(File(dir, "8.cbz").exists())
        assertFalse(File(dir, "8.cbz.part").exists())
        assertTrue(inserts.isEmpty())
    }
}
