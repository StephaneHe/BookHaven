package com.bookhaven.android.data.api

import retrofit2.HttpException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

fun Throwable.toUserMessage(): String = when (this) {
    is SocketTimeoutException -> "Server timeout — check your connection"
    is UnknownHostException -> "Cannot connect to server: ${message?.substringAfterLast(' ') ?: message}"
    is ConnectException -> "Cannot connect to server: ${message?.substringAfterLast(": ") ?: message}"
    is HttpException -> "Server error ${code()}: ${message()}"
    else -> message ?: "Unknown error"
}
