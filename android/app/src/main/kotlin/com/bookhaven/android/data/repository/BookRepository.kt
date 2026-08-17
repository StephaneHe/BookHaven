package com.bookhaven.android.data.repository

import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.data.api.model.BooksResponse
import com.bookhaven.android.data.api.model.CreateUserRequest
import com.bookhaven.android.data.api.model.LoginRequest
import com.bookhaven.android.data.api.model.ServerUser
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class BookRepository @Inject constructor(private val api: ApiService) {

    suspend fun getBooks(
        search: String? = null,
        category: String? = null,
        genre: String? = null,
        author: String? = null,
        format: String? = null,
        sort: String? = null
    ): BooksResponse = api.getBooks(
        search = search?.takeIf { it.isNotBlank() },
        category = category?.takeIf { it.isNotBlank() },
        genre = genre?.takeIf { it.isNotBlank() },
        author = author?.takeIf { it.isNotBlank() },
        format = format?.takeIf { it.isNotBlank() },
        sort = sort?.takeIf { it.isNotBlank() }
    )

    suspend fun getBookDetail(id: Int): Book = api.getBookDetail(id)

    suspend fun getContinueReading(): List<Book> =
        runCatching { api.getContinueReading() }.getOrDefault(emptyList())

    suspend fun getUsers(): List<ServerUser> = api.getUsers()

    suspend fun checkVersion() { api.getVersion() }

    /** Whether the server requires a login PIN (BOOKHAVEN_PIN set). */
    suspend fun pinRequired(): Boolean =
        runCatching { api.pinRequired().pinRequired }.getOrDefault(false)

    suspend fun login(username: String, pin: String? = null): Result<String> = runCatching {
        api.login(LoginRequest(username, pin?.takeIf { it.isNotBlank() })).userName
    }

    suspend fun logout() = runCatching { api.logout() }

    suspend fun getMe(): String? = runCatching { api.getMe().userName }.getOrNull()

    suspend fun createUser(username: String, pin: String? = null): Result<Unit> = runCatching {
        api.createUser(CreateUserRequest(username, pin?.takeIf { it.isNotBlank() })); Unit
    }

    suspend fun deleteProgress(bookId: Int): Result<Unit> = runCatching {
        api.deleteProgress(bookId); Unit
    }
}
