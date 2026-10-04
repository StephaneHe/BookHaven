package com.bookhaven.android

import com.bookhaven.android.data.api.model.SeriesRef
import com.bookhaven.android.ui.reader.ComicReaderLogic
import com.bookhaven.android.ui.reader.ComicReaderLogic.ChapterStep
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Locale

class ComicReaderLogicTest {

    // ── R93 (a): server webtoon flag has priority over image detection ──

    @Test fun R93_serverWebtoonFlagWinsWithoutRunningDetection() {
        var detected = 0
        assertTrue(ComicReaderLogic.useContinuousReader(true) { detected++; false })
        assertEquals("detection must not run when the server flags the book", 0, detected)
    }

    @Test fun R93_detectionUsedWhenServerFlagAbsentOrFalse() {
        var detected = 0
        assertTrue(ComicReaderLogic.useContinuousReader(null) { detected++; true })
        assertFalse(ComicReaderLogic.useContinuousReader(false) { detected++; false })
        assertTrue(ComicReaderLogic.useContinuousReader(false) { detected++; true })
        assertEquals(3, detected)
    }

    // ── R94 (b): position "plate.fraction" ──

    @Test fun R94_parsePlateAndFraction() {
        val (plate, frac) = ComicReaderLogic.parsePosition("3.4521", 10)
        assertEquals(3, plate)
        assertEquals(0.4521f, frac, 1e-4f)
    }

    @Test fun R94_parseIntegerPositionHasZeroFraction() {
        assertEquals(4 to 0f, ComicReaderLogic.parsePosition("4", 10))
    }

    @Test fun R94_parseGarbageOrMissingGivesZero() {
        assertEquals(0 to 0f, ComicReaderLogic.parsePosition("epubcfi(/6/4!/4/2)", 10))
        assertEquals(0 to 0f, ComicReaderLogic.parsePosition("", 10))
        assertEquals(0 to 0f, ComicReaderLogic.parsePosition(null, 10))
    }

    @Test fun R94_parseClampsToBookBounds() {
        assertEquals(9, ComicReaderLogic.parsePosition("57.5", 10).first)   // past the end -> last plate
        assertEquals(0 to 0f, ComicReaderLogic.parsePosition("-2.5", 10))   // negative -> start
        assertEquals(0.9999f, ComicReaderLogic.parsePosition("2.99999", 10).second, 0f)
    }

    @Test fun R94_formatUsesLocaleUsWithFourDecimals() {
        val saved = Locale.getDefault()
        try {
            Locale.setDefault(Locale.FRANCE)    // decimal comma locale must not leak in
            assertEquals("3.4521", ComicReaderLogic.formatPosition(3, 0.4521f))
            assertEquals("4.0000", ComicReaderLogic.formatPosition(4, 0f))
            assertEquals("0.9999", ComicReaderLogic.formatPosition(0, 0.9999f))
        } finally {
            Locale.setDefault(saved)
        }
    }

    @Test fun R94_formatThenParseRoundTrips() {
        val (p, f) = ComicReaderLogic.parsePosition(ComicReaderLogic.formatPosition(7, 0.25f), 20)
        assertEquals(7, p)
        assertEquals(0.25f, f, 1e-4f)
    }

    @Test fun R94_percentIs100OnlyWhenFinished() {
        assertEquals(100f, ComicReaderLogic.progressPercent(0, 0f, 10, finished = true), 0f)
        // At the very last plate's bottom but not flagged finished: capped at 99.
        assertEquals(99f, ComicReaderLogic.progressPercent(9, 0.9999f, 10, finished = false), 0f)
        assertEquals(99f, ComicReaderLogic.progressPercent(10, 0f, 10, finished = false), 0f)
    }

    @Test fun R94_percentClampedBetween1And99AndTruncated() {
        assertEquals(1f, ComicReaderLogic.progressPercent(0, 0f, 10, finished = false), 0f)     // start is never 0
        assertEquals(1f, ComicReaderLogic.progressPercent(0, 0.05f, 1000, finished = false), 0f)
        assertEquals(34f, ComicReaderLogic.progressPercent(3, 0.45f, 10, finished = false), 0f)  // 34.5 -> 34
        assertEquals(50f, ComicReaderLogic.progressPercent(5, 0f, 10, finished = false), 0f)
    }

    // ── R94 (c): stepping past the first/last chapter goes to the series neighbour ──

    private val prev = SeriesRef(1, "Chapitre 1", "cbz")
    private val next = SeriesRef(3, "Chapitre 3", "cbz")

    @Test fun R94_stepWithinFileStaysInFile() {
        assertEquals(ChapterStep.InFile(2), ComicReaderLogic.chapterStep(1, 1, 5, prev, next))
        assertEquals(ChapterStep.InFile(0), ComicReaderLogic.chapterStep(1, -1, 5, prev, next))
    }

    @Test fun R94_stepPastLastChapterOpensSeriesNext() {
        assertEquals(ChapterStep.Series(next), ComicReaderLogic.chapterStep(4, 1, 5, prev, next))
        assertEquals(ChapterStep.Series(next), ComicReaderLogic.chapterStep(0, 1, 1, prev, next))  // one-chapter file
    }

    @Test fun R94_stepBeforeFirstChapterOpensSeriesPrev() {
        assertEquals(ChapterStep.Series(prev), ComicReaderLogic.chapterStep(0, -1, 5, prev, next))
    }

    @Test fun R94_noNeighbourMeansNoMove() {
        assertEquals(ChapterStep.None, ComicReaderLogic.chapterStep(4, 1, 5, prev, null))
        assertEquals(ChapterStep.None, ComicReaderLogic.chapterStep(0, -1, 5, null, next))
    }

    // ── Zoom clamping (webtoon reader) ──

    @Test fun R93_zoomClampedTo40And400WithStep15() {
        assertEquals(40, ComicReaderLogic.ZOOM_MIN)
        assertEquals(400, ComicReaderLogic.ZOOM_MAX)
        assertEquals(15, ComicReaderLogic.ZOOM_STEP)
        assertEquals(100, ComicReaderLogic.clampZoom(100))
        assertEquals(40, ComicReaderLogic.clampZoom(25))
        assertEquals(40, ComicReaderLogic.clampZoom(-1000))
        assertEquals(400, ComicReaderLogic.clampZoom(415))
        // Repeated zoom-out from 100 stops at the floor.
        var z = 100
        repeat(10) { z = ComicReaderLogic.clampZoom(z - ComicReaderLogic.ZOOM_STEP) }
        assertEquals(40, z)
    }
}
