package com.bookhaven.android.di

import android.content.Context
import android.content.SharedPreferences
import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.api.MemoryCookieJar
import com.bookhaven.android.data.api.buildOkHttpClient
import com.bookhaven.android.data.api.buildRetrofit
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import javax.inject.Singleton

/** Single source of truth for the fallback server URL when none is saved in prefs. */
const val DEFAULT_SERVER_URL = "http://bookhaven-host:8097"

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideSharedPrefs(@ApplicationContext ctx: Context): SharedPreferences =
        ctx.getSharedPreferences("bookhaven_prefs", Context.MODE_PRIVATE)

    @Provides
    @Singleton
    fun provideCookieJar(): MemoryCookieJar = MemoryCookieJar()

    @Provides
    @Singleton
    fun provideOkHttpClient(cookieJar: MemoryCookieJar): OkHttpClient =
        buildOkHttpClient(cookieJar)

    @Provides
    @Singleton
    fun provideApiService(prefs: SharedPreferences, client: OkHttpClient): ApiService {
        val url = prefs.getString("server_url", DEFAULT_SERVER_URL)
            ?: DEFAULT_SERVER_URL
        return buildRetrofit(url, client).create(ApiService::class.java)
    }
}
