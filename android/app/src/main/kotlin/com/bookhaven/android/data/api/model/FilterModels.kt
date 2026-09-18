package com.bookhaven.android.data.api.model

/** Response of GET /api/filters: the full facet lists (server-wide, not the
 *  facets of one 50-item page). categories and genres are DISTINCT concepts. */
data class FiltersResponse(
    val categories: List<String> = emptyList(),
    val authors: List<String> = emptyList(),
    val genres: List<String> = emptyList(),
    val formats: List<String> = emptyList()
)
