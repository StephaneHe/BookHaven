package com.bookhaven.android.data.api.model

import com.google.gson.annotations.SerializedName

data class ScanStatus(
    @SerializedName("running") val running: Boolean = false,
    @SerializedName("current") val current: Int = 0,
    @SerializedName("total") val total: Int = 0,
    @SerializedName("message") val message: String = ""
)
