package com.bookhaven.android.ui.upload

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bookhaven.android.data.api.ApiService
import com.bookhaven.android.data.api.model.UploadAnalyzeResponse
import com.bookhaven.android.data.api.model.UploadConfirmRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import javax.inject.Inject

sealed class UploadState {
    object Idle : UploadState()
    object Analyzing : UploadState()
    data class Preview(val analysis: UploadAnalyzeResponse) : UploadState()
    object Confirming : UploadState()
    object Done : UploadState()
    data class Error(val message: String) : UploadState()
}

@HiltViewModel
class UploadViewModel @Inject constructor(private val api: ApiService) : ViewModel() {

    private val _state = MutableStateFlow<UploadState>(UploadState.Idle)
    val state: StateFlow<UploadState> = _state.asStateFlow()

    fun analyzeFile(uri: Uri, context: Context) {
        viewModelScope.launch {
            _state.value = UploadState.Analyzing
            runCatching {
                withContext(Dispatchers.IO) {
                    val cr = context.contentResolver
                    val name = getFileName(cr, uri) ?: "upload"
                    val mime = cr.getType(uri) ?: "application/octet-stream"
                    val bytes = cr.openInputStream(uri)?.readBytes() ?: error("Cannot read file")
                    val part = MultipartBody.Part.createFormData(
                        "file", name, bytes.toRequestBody(mime.toMediaTypeOrNull())
                    )
                    api.uploadAnalyze(part)
                }
            }.onSuccess { _state.value = UploadState.Preview(it) }
             .onFailure { _state.value = UploadState.Error(it.message ?: "Upload failed") }
        }
    }

    fun confirm(analysis: UploadAnalyzeResponse, title: String, author: String,
                category: String, series: String, genre: String) {
        viewModelScope.launch {
            _state.value = UploadState.Confirming
            runCatching {
                api.uploadConfirm(UploadConfirmRequest(analysis.uploadId, title, author, category, series, genre))
            }.onSuccess { _state.value = UploadState.Done }
             .onFailure { _state.value = UploadState.Error(it.message ?: "Confirm failed") }
        }
    }

    fun reset() { _state.value = UploadState.Idle }

    private fun getFileName(cr: android.content.ContentResolver, uri: Uri): String? {
        cr.query(uri, null, null, null, null)?.use { cursor ->
            val idx = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (cursor.moveToFirst() && idx >= 0) return cursor.getString(idx)
        }
        return uri.lastPathSegment
    }
}
