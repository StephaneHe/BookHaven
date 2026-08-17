package com.bookhaven.android.data.api.model

import com.google.gson.annotations.SerializedName

data class ProgressRequest(
    @SerializedName("progress") val progress: Float,
    @SerializedName("current_location") val currentLocation: String
)

data class ProgressResponse(
    @SerializedName("progress") val progress: Float = 0f,
    @SerializedName("current_location") val currentLocation: String = "",
    @SerializedName("last_read") val lastRead: String? = null
)
