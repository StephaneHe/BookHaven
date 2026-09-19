package com.bookhaven.android.data.api.model

import com.google.gson.annotations.SerializedName

/** Response of GET /api/books/<id>/comic-pages: ordered page (plate) names. */
data class ComicPagesResponse(
    val pages: List<String> = emptyList(),
    // Content fingerprint (file_size:modified_at). Bumps when the server rebuilds
    // the archive (e.g. a manhua CBZ regenerated with more pages) so the app can
    // invalidate its stale CBZ / page cache instead of serving old content.
    @SerializedName("content_version") val contentVersion: String = ""
)
