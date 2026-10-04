package com.bookhaven.android

import com.bookhaven.android.data.api.model.ComicPagesResponse
import com.bookhaven.android.ui.reader.ComicPageSource
import com.bookhaven.android.ui.reader.ComicReaderLogic
import com.bookhaven.android.ui.reader.NaturalOrder
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class ComicPageSourceTest {
    @get:Rule val tmp = TemporaryFolder()

    // ── R91: natural page order, identical to the server's scanner.natural_key ──

    @Test fun R91_naturalOrderMatchesServer() {
        val input = listOf("chap_10_p_0.jpg", "chap_2_p_10.jpg", "chap_2_p_2.jpg", "chap_1.jpg", "Chap_2_p_1.jpg")
        assertEquals(
            listOf("chap_1.jpg", "Chap_2_p_1.jpg", "chap_2_p_2.jpg", "chap_2_p_10.jpg", "chap_10_p_0.jpg"),
            input.sortedWith(NaturalOrder)
        )
    }

    @Test fun R91_zeroPaddedNamesKeepPlainOrder() {
        val padded = listOf("00010_002.jpg", "00002_010.jpg", "00002_001.jpg", "00001_000.jpg", "00010_001.jpg")
        assertEquals(padded.sorted(), padded.sortedWith(NaturalOrder))
        assertEquals(listOf("00001_000.jpg", "00002_001.jpg", "00002_010.jpg", "00010_001.jpg", "00010_002.jpg"),
            padded.sortedWith(NaturalOrder))
    }

    @Test fun R91_veryLongDigitRunsDoNotOverflow() {
        val big = "p_" + "9".repeat(40) + ".jpg"
        val bigger = "p_1" + "0".repeat(40) + ".jpg"
        val small = "p_2.jpg"
        assertEquals(listOf(small, big, bigger), listOf(bigger, big, small).sortedWith(NaturalOrder))
        assertTrue(NaturalOrder.compare(big, bigger) < 0)
        assertTrue(NaturalOrder.compare(bigger, big) > 0)
        // Same value, different padding, beyond Long range: numerically equal token.
        assertEquals(0, NaturalOrder.compare("p_" + "0".repeat(5) + "9".repeat(30), "p_" + "9".repeat(30)))
    }

    @Test fun R91_offlineCbzPagesComeOutInNaturalOrder() = runBlocking {
        val cbz = makeCbz("chap_10_p_0.jpg", "chap_2_p_10.jpg", "notes.txt", "chap_2_p_2.jpg", "chap_1.jpg", "Chap_2_p_1.jpg")
        val src = ComicPageSource(cacheContext(cacheRoot()), 7, FakeApi().api, cbz, "1:2")
        assertEquals(
            listOf("chap_1.jpg", "Chap_2_p_1.jpg", "chap_2_p_2.jpg", "chap_2_p_10.jpg", "chap_10_p_0.jpg"),
            src.pageNames()
        )
    }

    // ── R89: cache keyed by book id + content version; stale versions purged ──

    @Test fun R89_cacheFilesKeyedByBookAndContentVersion() = runBlocking {
        val root = cacheRoot()
        val cbz = makeCbz("a_1.jpg", "a_2.jpg")
        val src = ComicPageSource(cacheContext(root), 42, FakeApi().api, cbz, "1234:5678.9")
        val f = src.pageFile(1)
        assertNotNull(f)
        // Non-alphanumerics in the version are sanitised to '_'.
        assertEquals("b42_v1234_5678_9_p1.img", f!!.name)
        assertEquals(File(root, "comic_pages"), f.parentFile)
        assertEquals("a_2.jpg", f.readText())
    }

    @Test fun R89_blankContentVersionUsesZero() = runBlocking {
        val src = ComicPageSource(cacheContext(cacheRoot()), 3, FakeApi().api, makeCbz("x.jpg"), "")
        assertEquals("b3_v0_p0.img", src.pageFile(0)!!.name)
    }

    @Test fun R89_stalePagesOfOtherVersionsArePurgedOnConstruction() {
        val root = cacheRoot()
        val dir = File(root, "comic_pages").apply { mkdirs() }
        val stale = File(dir, "b42_vOLD_p0.img").apply { writeText("old") }
        val current = File(dir, "b42_vNEW_p0.img").apply { writeText("new") }
        val otherBook = File(dir, "b43_vOLD_p0.img").apply { writeText("other") }
        val prefixClash = File(dir, "b420_vOLD_p0.img").apply { writeText("other") }

        ComicPageSource(cacheContext(root), 42, FakeApi().api, null, "NEW")

        assertFalse("stale version of this book must be purged", stale.exists())
        assertTrue("current version must be kept", current.exists())
        assertTrue("other books untouched", otherBook.exists())
        assertTrue("book 420 is not book 42", prefixClash.exists())
    }

    @Test fun R89_cachedPageServedWithoutRefetch() = runBlocking {
        val root = cacheRoot()
        val dir = File(root, "comic_pages").apply { mkdirs() }
        File(dir, "b5_vV1_p0.img").writeText("cached")
        val api = FakeApi { error("network must not be used for a cached page") }
        val src = ComicPageSource(cacheContext(root), 5, api.api, null, "V1", listOf("p0.jpg"))
        assertEquals("cached", src.pageFile(0)!!.readText())
        assertTrue(api.calls.isEmpty())
    }

    @Test fun R89_onlinePagesComeFromApiWhenNoKnownNames() = runBlocking {
        val api = FakeApi { c ->
            if (c.name == "getComicPages") ComicPagesResponse(pages = listOf("p1.jpg", "p2.jpg")) else null
        }
        val src = ComicPageSource(cacheContext(cacheRoot()), 9, api.api, null, "v")
        assertEquals(2, src.pageCount())
        assertEquals(listOf(9), api.callsTo("getComicPages").single().args)
    }

    // ── R90: offline copy stale when the server content version differs ──

    @Test fun R90_contentVersionComparison() {
        assertTrue(ComicReaderLogic.isOfflineCopyStale("100:1", "200:2"))
        assertTrue(ComicReaderLogic.isOfflineCopyStale("", "200:2"))      // never versioned locally
        assertFalse(ComicReaderLogic.isOfflineCopyStale("200:2", "200:2"))
        assertFalse(ComicReaderLogic.isOfflineCopyStale("100:1", ""))     // server gave no version
        assertFalse(ComicReaderLogic.isOfflineCopyStale("100:1", "   "))
    }

    private fun cacheRoot(): File = tmp.newFolder()

    private fun makeCbz(vararg names: String): File {
        val f = File(tmp.newFolder(), "book.cbz")
        ZipOutputStream(f.outputStream()).use { z ->
            names.forEach { n -> z.putNextEntry(ZipEntry(n)); z.write(n.toByteArray()); z.closeEntry() }
        }
        return f
    }
}
