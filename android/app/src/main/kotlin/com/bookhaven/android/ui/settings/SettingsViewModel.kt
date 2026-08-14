package com.bookhaven.android.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.api.model.ScanStatus
import com.bookhaven.android.data.repository.BookRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val api: ApiService,
    private val bookRepo: BookRepository
) : ViewModel() {

    private val _scanStatus = MutableStateFlow<ScanStatus?>(null)
    val scanStatus: StateFlow<ScanStatus?> = _scanStatus.asStateFlow()

    private val _toast = MutableStateFlow<String?>(null)
    val toast: StateFlow<String?> = _toast.asStateFlow()

    fun triggerScan() {
        viewModelScope.launch {
            runCatching { api.triggerScan() }
                .onSuccess { pollScanStatus() }
                .onFailure { _toast.value = "Scan failed: ${it.message}" }
        }
    }

    private fun pollScanStatus() {
        viewModelScope.launch {
            repeat(120) {
                delay(2000)
                runCatching { api.getScanStatus() }.onSuccess { status ->
                    _scanStatus.value = status
                    if (!status.running) return@launch
                }
            }
        }
    }

    fun createUser(username: String) {
        viewModelScope.launch {
            bookRepo.createUser(username)
                .onSuccess { _toast.value = "Account '$username' created" }
                .onFailure { _toast.value = "Failed: ${it.message}" }
        }
    }

    fun clearToast() { _toast.value = null }
}
