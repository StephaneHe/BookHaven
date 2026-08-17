package com.bookhaven.android.data.api

import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.data.api.model.BooksResponse
import com.bookhaven.android.data.api.model.CreateUserRequest
import com.bookhaven.android.data.api.model.LoginRequest
import com.bookhaven.android.data.api.model.LoginResponse
import com.bookhaven.android.data.api.model.MeResponse
import com.bookhaven.android.data.api.model.PinRequiredResponse
import com.bookhaven.android.data.api.model.ProgressRequest
import com.bookhaven.android.data.api.model.ProgressResponse
import com.bookhaven.android.data.api.model.ScanStatus
import com.bookhaven.android.data.api.model.ServerUser
import com.bookhaven.android.data.api.model.UploadAnalyzeResponse
import com.bookhaven.android.data.api.model.UploadConfirmRequest
import okhttp3.MultipartBody
import okhttp3.ResponseBody
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.Streaming

interface ApiService {

    @GET("api/books")
    suspend fun getBooks(
        @Query("search") search: String? = null,
        @Query("category") category: String? = null,
        @Query("genre") genre: String? = null,
        @Query("author") author: String? = null,
        @Query("format") format: String? = null,
        @Query("sort") sort: String? = null,
        @Query("page") page: Int = 1,
        @Query("per_page") perPage: Int = 50
    ): BooksResponse

    @GET("api/books/{id}")
    suspend fun getBookDetail(@Path("id") id: Int): Book

    @GET("api/continue-reading")
    suspend fun getContinueReading(): List<Book>

    @GET("api/auth/users")
    suspend fun getUsers(): List<ServerUser>

    @GET("api/auth/pin-required")
    suspend fun pinRequired(): PinRequiredResponse

    @POST("api/auth/login")
    suspend fun login(@Body body: LoginRequest): LoginResponse

    @POST("api/auth/logout")
    suspend fun logout(): ResponseBody

    @GET("api/auth/me")
    suspend fun getMe(): MeResponse

    @POST("api/auth/users")
    suspend fun createUser(@Body body: CreateUserRequest): ResponseBody

    @Streaming
    @GET("api/books/{id}/file")
    suspend fun downloadBook(@Path("id") id: Int): ResponseBody

    @GET("api/books/{id}/progress")
    suspend fun getProgress(@Path("id") id: Int): ProgressResponse

    @PUT("api/books/{id}/progress")
    suspend fun setProgress(@Path("id") id: Int, @Body body: ProgressRequest): ResponseBody

    @DELETE("api/books/{id}/progress")
    suspend fun deleteProgress(@Path("id") id: Int): ResponseBody

    @POST("api/scan")
    suspend fun triggerScan(): ResponseBody

    @GET("api/scan/status")
    suspend fun getScanStatus(): ScanStatus

    @Multipart
    @POST("api/upload/analyze")
    suspend fun uploadAnalyze(@Part file: MultipartBody.Part): UploadAnalyzeResponse

    @POST("api/upload/confirm")
    suspend fun uploadConfirm(@Body body: UploadConfirmRequest): ResponseBody

    @GET("api/version")
    suspend fun getVersion(): ResponseBody
}
