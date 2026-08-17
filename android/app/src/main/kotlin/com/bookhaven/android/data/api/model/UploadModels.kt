package com.bookhaven.android.data.api.model

import com.google.gson.annotations.SerializedName

data class UploadAnalyzeResponse(
    @SerializedName("upload_id") val uploadId: String = "",
    @SerializedName("title") val title: String = "",
    @SerializedName("author") val author: String = "",
    @SerializedName("format") val format: String = "",
    @SerializedName("category") val category: String = "",
    @SerializedName("series") val series: String = "",
    @SerializedName("genre") val genre: String = "",
    @SerializedName("filename") val filename: String = "",
    @SerializedName("suggested_path") val suggestedPath: String = ""
)

data class UploadConfirmRequest(
    @SerializedName("upload_id") val uploadId: String,
    @SerializedName("title") val title: String,
    @SerializedName("author") val author: String,
    @SerializedName("category") val category: String,
    @SerializedName("series") val series: String,
    @SerializedName("genre") val genre: String
)
