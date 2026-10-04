package com.bookhaven.android

import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.ui.reader.ComicReaderFragment
import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class WebtoonReaderModelTest {
    private val gson = Gson()

    @Test fun progressAsNumber() {
        assertEquals(37.5f, gson.fromJson("""{"id":1,"title":"t","progress":37.5}""", Book::class.java).progress)
    }

    @Test fun progressAsObjectFromBookDetail() {
        val b = gson.fromJson(
            """{"id":1,"title":"t","progress":{"progress":42.0,"current_location":"3.5000"},
               "webtoon":true,"series_prev":null,"series_next":{"id":2,"title":"Chapitre 2","format":"cbz"}}""",
            Book::class.java)
        assertEquals(42f, b.progress)
        assertTrue(b.webtoon)
        assertNull(b.seriesPrev)
        assertEquals(2, b.seriesNext?.id)
        assertEquals("Chapitre 2", b.seriesNext?.title)
    }

    @Test fun progressNull() {
        val b = gson.fromJson("""{"id":1,"title":"t","progress":null}""", Book::class.java)
        assertEquals(0f, b.progress)
        assertFalse(b.webtoon)
    }

    @Test fun webtoonRuleMatchesTheWeb() {
        assertTrue(ComicReaderFragment.isWebtoon(listOf(1200 to 800, 400 to 2400, 400 to 2400, 400 to 2400)))
        assertTrue(ComicReaderFragment.isWebtoon(listOf(700 to 1000, 400 to 2400, 400 to 2400, 400 to 2400)))
        assertFalse(ComicReaderFragment.isWebtoon(listOf(700 to 1000, 700 to 1000)))
        assertFalse(ComicReaderFragment.isWebtoon(listOf(700 to 1000, 400 to 2400)))
        assertFalse(ComicReaderFragment.isWebtoon(emptyList()))
    }
}
