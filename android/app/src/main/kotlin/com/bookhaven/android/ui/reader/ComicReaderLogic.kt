package com.bookhaven.android.ui.reader

import com.bookhaven.android.data.api.model.SeriesRef
import java.util.Locale

/**
 * Pure decisions of [ComicReaderFragment], kept free of Android types so they can be
 * unit-tested on the JVM. The Fragment only wires these to views / repositories.
 */
internal object ComicReaderLogic {
    const val ZOOM_MIN = 40
    const val ZOOM_MAX = 400
    const val ZOOM_STEP = 15

    /** Webtoon zoom is always kept within [ZOOM_MIN]..[ZOOM_MAX] percent. */
    fun clampZoom(z: Int): Int = z.coerceIn(ZOOM_MIN, ZOOM_MAX)

    /**
     * The server flag (series/category) is authoritative: a flagged book never falls
     * back to the paged reader and [detect] (image sampling) is not even run.
     */
    inline fun useContinuousReader(serverWebtoon: Boolean?, detect: () -> Boolean): Boolean =
        serverWebtoon == true || detect()

    /** Offline copy is stale when the server reports a different, non-blank content version. */
    fun isOfflineCopyStale(storedVersion: String, serverVersion: String): Boolean =
        serverVersion.isNotBlank() && serverVersion != storedVersion

    /**
     * Stored position -> (plate, fraction). A plate index (paged) or "plate.fraction"
     * (webtoon scroll position, as the web). Unparseable -> plate 0, fraction 0.
     */
    fun parsePosition(stored: String?, totalPages: Int): Pair<Int, Float> {
        val v = stored?.toDoubleOrNull() ?: 0.0
        val plate = v.toInt().coerceIn(0, totalPages - 1)
        val frac = (v - v.toInt()).toFloat().coerceIn(0f, 0.9999f)
        return plate to frac
    }

    /** "plate.fraction" with exactly 4 decimals, always with a '.' (Locale.US). */
    fun formatPosition(globalIdx: Int, frac: Float): String =
        String.format(Locale.US, "%.4f", globalIdx + frac.toDouble())

    /** Webtoon %: 100 only when finished, otherwise clamped to 1..99 (whole numbers). */
    fun progressPercent(globalIdx: Int, frac: Float, totalPages: Int, finished: Boolean): Float {
        val v = globalIdx + frac.toDouble()
        return if (finished) 100f
               else (v / totalPages * 100).toFloat().coerceIn(1f, 99f).toInt().toFloat()
    }

    sealed interface ChapterStep {
        data class InFile(val index: Int) : ChapterStep
        data class Series(val ref: SeriesRef) : ChapterStep
        object None : ChapterStep
    }

    /** Previous/next chapter of this file, then previous/next book of the series. */
    fun chapterStep(
        chapterIdx: Int, dir: Int, chapterCount: Int,
        seriesPrev: SeriesRef?, seriesNext: SeriesRef?,
    ): ChapterStep {
        val target = chapterIdx + dir
        if (target in 0 until chapterCount) return ChapterStep.InFile(target)
        val sib = if (dir < 0) seriesPrev else seriesNext
        return sib?.let { ChapterStep.Series(it) } ?: ChapterStep.None
    }
}
