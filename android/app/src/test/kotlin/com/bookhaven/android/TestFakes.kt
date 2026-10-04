package com.bookhaven.android

import android.content.ContextWrapper
import android.content.SharedPreferences
import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.db.dao.ReadingProgressDao
import com.bookhaven.android.data.db.entity.ReadingProgress
import okhttp3.ResponseBody.Companion.toResponseBody
import retrofit2.HttpException
import retrofit2.Response
import java.io.File
import java.lang.reflect.Proxy

fun stripContinuation(args: Array<out Any?>?): List<Any?> {
    val l = args?.toList() ?: return emptyList()
    return if (l.lastOrNull() is kotlin.coroutines.Continuation<*>) l.dropLast(1) else l
}

/** One recorded ApiService call: method name + arguments (Continuation stripped). */
data class ApiCall(val name: String, val args: List<Any?>)

/**
 * Dynamic-proxy ApiService (no mocking library). For suspend methods the proxy simply
 * returns the value / throws synchronously, which Kotlin accepts as a non-suspending
 * completion. Throw only unchecked exceptions from [handler].
 */
class FakeApi(private val handler: (ApiCall) -> Any? = { null }) {
    val calls = mutableListOf<ApiCall>()
    val api: ApiService = Proxy.newProxyInstance(
        ApiService::class.java.classLoader, arrayOf(ApiService::class.java)
    ) { proxy, m, args ->
        when (m.name) {
            "toString" -> "FakeApi"
            "hashCode" -> System.identityHashCode(proxy)
            "equals" -> proxy === args?.get(0)
            else -> {
                val call = ApiCall(m.name, stripContinuation(args))
                calls += call
                handler(call)
            }
        }
    } as ApiService

    fun callsTo(name: String) = calls.filter { it.name == name }
}

fun http(code: Int): HttpException =
    HttpException(Response.error<Any>(code, "".toResponseBody(null)))

/** Generic proxy for any interface; every call goes to [handler] (Continuation stripped). */
inline fun <reified T> proxyOf(crossinline handler: (String, List<Any?>) -> Any?): T =
    Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { proxy, m, args ->
        when (m.name) {
            "toString" -> T::class.java.simpleName
            "hashCode" -> System.identityHashCode(proxy)
            "equals" -> proxy === args?.get(0)
            else -> handler(m.name, stripContinuation(args))
        }
    } as T

/** In-memory ReadingProgressDao. */
class FakeProgressDao(vararg initial: ReadingProgress) : ReadingProgressDao {
    val rows = linkedMapOf<Int, ReadingProgress>().apply { initial.forEach { put(it.bookId, it) } }
    val upserts = mutableListOf<ReadingProgress>()
    override suspend fun upsert(progress: ReadingProgress) { upserts += progress; rows[progress.bookId] = progress }
    override suspend fun getById(bookId: Int) = rows[bookId]
    override suspend fun getAll() = rows.values.toList()
    override suspend fun getPending() = rows.values.filter { it.pendingSync }
    override suspend fun deleteById(bookId: Int) { rows.remove(bookId) }
}

/** A Context whose only working method is getCacheDir() (enough for ComicPageSource). */
fun cacheContext(dir: File) = object : ContextWrapper(null) {
    override fun getCacheDir(): File = dir
    override fun getFilesDir(): File = dir
}

/** Map-backed SharedPreferences. */
fun fakePrefs(initial: Map<String, Any?> = emptyMap()): SharedPreferences {
    val data = HashMap(initial)
    lateinit var editor: SharedPreferences.Editor
    editor = proxyOf { name, args ->
        when (name) {
            "putString", "putInt", "putBoolean", "putLong", "putFloat" -> { data[args[0] as String] = args[1]; editor }
            "remove" -> { data.remove(args[0] as String); editor }
            "clear" -> { data.clear(); editor }
            "commit" -> true
            else -> null   // apply()
        }
    }
    return proxyOf { name, args ->
        when (name) {
            "edit" -> editor
            "contains" -> data.containsKey(args[0])
            "getAll" -> data.toMap()
            else -> if (data.containsKey(args[0])) data[args[0]] else args.getOrNull(1)
        }
    }
}
