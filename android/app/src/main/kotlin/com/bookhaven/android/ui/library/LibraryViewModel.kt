package com.bookhaven.android.ui.library

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bookhaven.android.data.api.toUserMessage
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.data.db.entity.DownloadedBook
import com.bookhaven.android.data.repository.BookRepository
import com.bookhaven.android.data.repository.DownloadRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import retrofit2.HttpException
import javax.inject.Inject

private const val TAG = "LibraryViewModel"

sealed class LibraryState {
    object Loading : LibraryState()
    data class Success(
        val books: List<Book>,
        val categories: List<String>,
        val genres: List<String>,
        val formats: List<String>
    ) : LibraryState()
    data class Error(val message: String) : LibraryState()
}

@HiltViewModel
class LibraryViewModel @Inject constructor(
    private val bookRepo: BookRepository,
    private val downloadRepo: DownloadRepository
) : ViewModel() {

    private val _state = MutableStateFlow<LibraryState>(LibraryState.Loading)
    val state: StateFlow<LibraryState> = _state.asStateFlow()

    private val _continueReading = MutableStateFlow<List<Book>>(emptyList())
    val continueReading: StateFlow<List<Book>> = _continueReading.asStateFlow()

    val downloads: StateFlow<List<DownloadedBook>> = downloadRepo.downloads
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _downloading = MutableStateFlow<Set<Int>>(emptySet())
    val downloading: StateFlow<Set<Int>> = _downloading.asStateFlow()

    private val _toast = MutableStateFlow<String?>(null)
    val toast: StateFlow<String?> = _toast.asStateFlow()

    // Emitted when the server rejects a request with 401 → the UI routes back to login.
    private val _sessionExpired = MutableSharedFlow<Unit>()
    val sessionExpired: SharedFlow<Unit> = _sessionExpired.asSharedFlow()

    var currentSearch: String = ""
    var currentCategory: String = ""
    var currentGenre: String = ""
    var currentFormat: String = ""

    init { loadAll() }

    fun loadAll() {
        loadBooks()
        loadContinueReading()
    }

    fun loadBooks(
        search: String = currentSearch,
        category: String = currentCategory,
        genre: String = currentGenre,
        format: String = currentFormat
    ) {
        currentSearch = search; currentCategory = category
        currentGenre = genre; currentFormat = format
        val unfiltered = search.isBlank() && category.isBlank() && genre.isBlank() && format.isBlank()
        viewModelScope.launch {
            // Only flash the spinner when we have nothing to show yet, so switching tabs
            // back to the library doesn't blank out already-loaded content.
            if (_state.value !is LibraryState.Success) _state.value = LibraryState.Loading
            runCatching {
                bookRepo.getBooks(
                    search = search.takeIf { it.isNotBlank() },
                    category = category.takeIf { it.isNotBlank() },
                    genre = genre.takeIf { it.isNotBlank() },
                    format = format.takeIf { it.isNotBlank() }
                )
            }.onSuccess { resp ->
                val books = resp.books
                _state.value = buildSuccess(books)
                // Refresh the offline snapshot only on a full, unfiltered load.
                if (unfiltered) runCatching { downloadRepo.cacheLibrary(books) }
            }.onFailure { e ->
                Log.e(TAG, "loadBooks() failed", e)
                when {
                    e is HttpException && e.code() == 401 ->
                        _sessionExpired.emit(Unit)   // Fix 4 — route back to login, no error dialog
                    else -> {
                        // Network/server error: fall back to the cached library instead of failing.
                        val cached = runCatching { downloadRepo.getCachedLibrary() }.getOrDefault(emptyList())
                        if (cached.isNotEmpty()) {
                            _state.value = buildSuccess(cached)
                            _toast.value = "Mode hors-ligne"
                        } else {
                            _state.value = LibraryState.Error(e.toUserMessage())
                        }
                    }
                }
            }
        }
    }

    private fun buildSuccess(books: List<Book>) = LibraryState.Success(
        books = books,
        categories = listOf("") + books.map { it.category }.filter { it.isNotBlank() }.distinct().sorted(),
        genres = listOf("") + books.map { it.genre }.filter { it.isNotBlank() }.distinct().sorted(),
        formats = listOf("") + books.map { it.format }.filter { it.isNotBlank() }.distinct().sorted()
    )

    fun loadContinueReading() {
        viewModelScope.launch {
            _continueReading.value = bookRepo.getContinueReading()
        }
    }

    fun downloadBook(book: Book) {
        if (_downloading.value.contains(book.id)) return
        viewModelScope.launch {
            _downloading.value = _downloading.value + book.id
            downloadRepo.downloadBook(book)
                .onSuccess { _toast.value = "Downloaded: ${book.title}" }
                .onFailure { e ->
                    Log.e(TAG, "downloadBook(${book.id}) failed", e)
                    _toast.value = "Download failed: ${e.toUserMessage()}"
                }
            _downloading.value = _downloading.value - book.id
        }
    }

    fun clearToast() { _toast.value = null }
}
