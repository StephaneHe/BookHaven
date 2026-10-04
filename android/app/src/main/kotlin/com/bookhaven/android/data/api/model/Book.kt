package com.bookhaven.android.data.api.model

import com.google.gson.TypeAdapter
import com.google.gson.annotations.JsonAdapter
import com.google.gson.annotations.SerializedName
import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import com.google.gson.stream.JsonWriter

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
    // A number in lists (/api/continue-reading), an object {progress, current_location, ...}
    // or null in GET /api/books/<id>: parsed leniently so the detail call no longer fails.
    @JsonAdapter(FlexibleProgressAdapter::class)
    @SerializedName("progress") val progress: Float = 0f,
    @SerializedName("current_location") val currentLocation: String = "",
    @SerializedName("last_read") val lastRead: String = "",
    // Content fingerprint (file_size:modified_at) — see ComicPagesResponse.
    @SerializedName("content_version") val contentVersion: String = "",
    // Book detail only: manhua / manhwa / webtoon = always the continuous vertical reader.
    @SerializedName("webtoon") val webtoon: Boolean = false,
    @SerializedName("series_prev") val seriesPrev: SeriesRef? = null,
    @SerializedName("series_next") val seriesNext: SeriesRef? = null
)

/** Previous / next book of the same series (GET /api/books/<id>). */
data class SeriesRef(
    @SerializedName("id") val id: Int,
    @SerializedName("title") val title: String = "",
    @SerializedName("format") val format: String = ""
)

/** Reads a progress percentage from a number, an object holding "progress", or null. */
class FlexibleProgressAdapter : TypeAdapter<Float>() {
    override fun write(out: JsonWriter, value: Float?) { out.value(value ?: 0f) }

    override fun read(reader: JsonReader): Float = when (reader.peek()) {
        JsonToken.NUMBER -> reader.nextDouble().toFloat()
        JsonToken.STRING -> reader.nextString().toFloatOrNull() ?: 0f
        JsonToken.BEGIN_OBJECT -> {
            var p = 0f
            reader.beginObject()
            while (reader.hasNext()) {
                if (reader.nextName() == "progress" && reader.peek() == JsonToken.NUMBER) {
                    p = reader.nextDouble().toFloat()
                } else reader.skipValue()
            }
            reader.endObject()
            p
        }
        else -> { reader.skipValue(); 0f }
    }
}

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
