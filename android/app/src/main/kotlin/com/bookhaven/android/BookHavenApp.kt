package com.bookhaven.android

import android.app.Application
import android.webkit.WebView
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.disk.DiskCache
import com.bookhaven.android.data.network.NetworkMonitor
import com.bookhaven.android.data.repository.SyncRepository
import dagger.hilt.android.HiltAndroidApp
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.drop
import kotlinx.coroutines.flow.filter
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import javax.inject.Inject

@HiltAndroidApp
class BookHavenApp : Application(), ImageLoaderFactory {

    @Inject lateinit var networkMonitor: NetworkMonitor
    @Inject lateinit var syncRepo: SyncRepository
    // The same authenticated client Retrofit uses: it carries the session cookie
    // (via PersistentCookieJar). Coil's default client has no cookie jar, so
    // /api/books/<id>/cover came back 401 and every cover fell to the placeholder.
    @Inject lateinit var okHttpClient: OkHttpClient

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onCreate() {
        super.onCreate()
        WebView.setWebContentsDebuggingEnabled(true)
        networkMonitor.start()
        // Initial sync on startup and again whenever network comes back online
        appScope.launch { syncRepo.syncAll() }
        appScope.launch {
            networkMonitor.isOnline
                .drop(1)                    // skip initial value
                .distinctUntilChanged()
                .filter { it }              // only react to becoming online
                .collect { syncRepo.syncAll() }
        }
    }

    /**
     * Coil's singleton image loader. Uses the authenticated OkHttp client so
     * cover requests are logged in, plus a persistent on-disk cache so covers
     * stay visible across process restarts (and reload cleanly when evicted)
     * instead of blinking out after a while.
     */
    override fun newImageLoader(): ImageLoader =
        ImageLoader.Builder(this)
            .okHttpClient(okHttpClient)
            .diskCache(
                DiskCache.Builder()
                    .directory(cacheDir.resolve("cover_cache"))
                    .maxSizeBytes(64L * 1024 * 1024)
                    .build()
            )
            .crossfade(true)
            .build()
}
