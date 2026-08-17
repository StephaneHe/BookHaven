package com.bookhaven.android.data.api.model

import com.google.gson.annotations.SerializedName

data class Book(
    @SerializedName("id") val id: Int,
    @SerializedName("title") val title: String,
    @SerializedName("author") val author: String = "",
    @SerializedName("format") val format: String = "",
    @SerializedName("has_cover") val hasCover: Boolean = false,
    @SerializedName("filename") val filename: String = "",
    @SerializedName("category") val category: String = "",
    @SerializedName("genre") val genre: String = "",
    @SerializedName("series") val series: String = "",
    @SerializedName("series_index") val seriesIndex: Float = 0f,
    @SerializedName("file_size") val fileSize: Long = 0L,
    @SerializedName("added_at") val addedAt: String = "",
    @SerializedName("volume_count") val volumeCount: Int = 0,
    @SerializedName("progress") val progress: Float = 0f,
    @SerializedName("current_location") val currentLocation: String = "",
    @SerializedName("last_read") val lastRead: String = ""
)

data class BooksResponse(
    @SerializedName("books") val books: List<Book> = emptyList(),
    @SerializedName("total") val total: Int = 0,
    @SerializedName("page") val page: Int = 1,
    @SerializedName("pages") val pages: Int = 1
)

data class ServerUser(
    @SerializedName("id") val id: String = "",
    @SerializedName("name") val name: String = ""
)
// pin is null when the server has no BOOKHAVEN_PIN configured; Gson omits null
// fields, so the body matches the pre-PIN client exactly in that case.
data class LoginRequest(
    @SerializedName("username") val username: String,
    @SerializedName("pin") val pin: String? = null
)
data class LoginResponse(
    @SerializedName("ok") val ok: Boolean = false,
    @SerializedName("user_id") val userId: String = "",
    @SerializedName("user_name") val userName: String = ""
)
data class MeResponse(
    @SerializedName("ok") val ok: Boolean = false,
    @SerializedName("user_id") val userId: String = "",
    @SerializedName("user_name") val userName: String = ""
)
data class CreateUserRequest(
    @SerializedName("name") val name: String,
    @SerializedName("pin") val pin: String? = null
)
data class PinRequiredResponse(@SerializedName("pin_required") val pinRequired: Boolean = false)
