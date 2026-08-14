package com.bookhaven.android

import android.app.Application
import android.webkit.WebView
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
import javax.inject.Inject

@HiltAndroidApp
class BookHavenApp : Application() {

    @Inject lateinit var networkMonitor: NetworkMonitor
    @Inject lateinit var syncRepo: SyncRepository

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
}
