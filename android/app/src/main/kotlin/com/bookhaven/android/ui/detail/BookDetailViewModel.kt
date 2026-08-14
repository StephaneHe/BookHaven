package com.bookhaven.android.ui.detail

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.data.repository.BookRepository
import com.bookhaven.android.data.repository.DownloadRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed class DetailState {
    object Loading : DetailState()
    data class Success(val book: Book) : DetailState()
    data class Error(val message: String) : DetailState()
}

@HiltViewModel
class BookDetailViewModel @Inject constructor(
    private val bookRepo: BookRepository,
    private val downloadRepo: DownloadRepository
) : ViewModel() {

    private val _state = MutableStateFlow<DetailState>(DetailState.Loading)
    val state: StateFlow<DetailState> = _state.asStateFlow()

    private val _toast = MutableStateFlow<String?>(null)
    val toast: StateFlow<String?> = _toast.asStateFlow()

    fun loadBook(bookId: Int) {
        viewModelScope.launch {
            _state.value = DetailState.Loading
            runCatching { bookRepo.getBookDetail(bookId) }
                .onSuccess { _state.value = DetailState.Success(it) }
                .onFailure { _state.value = DetailState.Error(it.message ?: "Error") }
        }
    }

    fun downloadBook(book: Book) {
        viewModelScope.launch {
            downloadRepo.downloadBook(book)
                .onSuccess { _toast.value = "Downloaded: ${book.title}" }
                .onFailure { _toast.value = "Failed: ${it.message}" }
        }
    }

    fun removeProgress(bookId: Int) {
        viewModelScope.launch {
            bookRepo.deleteProgress(bookId)
                .onSuccess { _toast.value = "Removed from reading list" }
                .onFailure { _toast.value = "Failed: ${it.message}" }
        }
    }

    fun clearToast() { _toast.value = null }
}
