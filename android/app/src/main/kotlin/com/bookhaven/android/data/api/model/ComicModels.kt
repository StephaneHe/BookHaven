package com.bookhaven.android.data.api.model

/** Response of GET /api/books/<id>/comic-pages: ordered page (plate) names. */
data class ComicPagesResponse(
    val pages: List<String> = emptyList()
)
