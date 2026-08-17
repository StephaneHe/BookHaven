package com.bookhaven.android.data.api

import android.webkit.CookieManager
import com.google.gson.GsonBuilder
import com.google.gson.TypeAdapter
import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import com.google.gson.stream.JsonWriter
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

class MemoryCookieJar : CookieJar {
    private val store = mutableMapOf<String, MutableList<Cookie>>()

    override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
        store.getOrPut(url.host) { mutableListOf() }.apply {
            removeAll { existing -> cookies.any { it.name == existing.name } }
            addAll(cookies)
        }
        // Mirror cookies into the WebView cookie store so the EPUB reader WebView —
        // which fetches /api/books/<id>/file itself — carries the same session cookie.
        val cm = CookieManager.getInstance()
        cookies.forEach { cm.setCookie(url.toString(), it.toString()) }
        cm.flush()
    }

    override fun loadForRequest(url: HttpUrl): List<Cookie> =
        store[url.host] ?: emptyList()

    fun clear() = store.clear()
}

fun buildOkHttpClient(cookieJar: CookieJar): OkHttpClient =
    OkHttpClient.Builder()
        .cookieJar(cookieJar)
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        })
        .build()

/**
 * SQLite has no boolean type, so the server serializes flags like `has_cover` as
 * integers 0/1. Gson's strict boolean reader rejects NUMBER tokens, so we install
 * a lenient adapter that accepts 0/1, "true"/"false"/"1"/"0", real booleans, and null.
 */
private val lenientBooleanAdapter = object : TypeAdapter<Boolean>() {
    override fun write(out: JsonWriter, value: Boolean?) {
        if (value == null) out.nullValue() else out.value(value)
    }

    override fun read(reader: JsonReader): Boolean? = when (reader.peek()) {
        JsonToken.NULL -> { reader.nextNull(); null }
        JsonToken.NUMBER -> reader.nextInt() != 0
        JsonToken.STRING -> reader.nextString().let { it == "true" || it == "1" }
        JsonToken.BOOLEAN -> reader.nextBoolean()
        else -> { reader.skipValue(); false }
    }
}

fun buildRetrofit(baseUrl: String, client: OkHttpClient): Retrofit {
    val gson = GsonBuilder()
        // primitive kotlin.Boolean (non-null fields)
        .registerTypeAdapter(Boolean::class.java, lenientBooleanAdapter)
        // boxed java.lang.Boolean (nullable Boolean? fields)
        .registerTypeAdapter(Boolean::class.javaObjectType, lenientBooleanAdapter)
        .create()
    return Retrofit.Builder()
        .baseUrl(if (baseUrl.endsWith("/")) baseUrl else "$baseUrl/")
        .client(client)
        .addConverterFactory(GsonConverterFactory.create(gson))
        .build()
}
