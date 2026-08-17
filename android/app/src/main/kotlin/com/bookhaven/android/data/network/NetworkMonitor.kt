package com.bookhaven.android.data.network

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class NetworkMonitor @Inject constructor(
    @ApplicationContext private val context: Context
) {
    private val _isOnline = MutableStateFlow(false)
    val isOnline: StateFlow<Boolean> = _isOnline.asStateFlow()

    fun start() {
        val cm = context.getSystemService(ConnectivityManager::class.java)
        cm.registerNetworkCallback(
            NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build(),
            object : ConnectivityManager.NetworkCallback() {
                override fun onAvailable(network: Network) { _isOnline.value = true }
                override fun onLost(network: Network) {
                    val active = cm.activeNetwork?.let {
                        cm.getNetworkCapabilities(it)
                            ?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                    } ?: false
                    if (!active) _isOnline.value = false
                }
            }
        )
        _isOnline.value = cm.activeNetwork?.let {
            cm.getNetworkCapabilities(it)
                ?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
        } ?: false
    }
}
