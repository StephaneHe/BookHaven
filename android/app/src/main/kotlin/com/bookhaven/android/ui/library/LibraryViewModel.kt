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
        val hasMore: Boolean,
        val total: Int
    ) : LibraryState()
    data class Error(val message: String) : LibraryState()
}

/** Server-wide facets. categories and genres are DISTINCT filter dimensions. */
data class Facets(
    val categories: List<String> = emptyList(),
    val genres: List<String> = emptyList(),
    val formats: List<String> = emptyList()
)

@HiltViewModel
class LibraryViewModel @Inject constructor(
    private val bookRepo: BookRepository,
    private val downloadRepo: DownloadRepository
) : ViewModel() {

    private val _state = MutableStateFlow<LibraryState>(LibraryState.Loading)
    val state: StateFlow<LibraryState> = _state.asStateFlow()

    val downloads: StateFlow<List<DownloadedBook>> = downloadRepo.downloads
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    private val _downloading = MutableStateFlow<Set<Int>>(emptySet())
    val downloading: StateFlow<Set<Int>> = _downloading.asStateFlow()

    private val _toast = MutableStateFlow<String?>(null)
    val toast: StateFlow<String?> = _toast.asStateFlow()

    // Emitted when the server rejects a request with 401 → the UI routes back to login.
    private val _sessionExpired = MutableSharedFlow<Unit>()
    val sessionExpired: SharedFlow<Unit> = _sessionExpired.asSharedFlow()

    private val _facets = MutableStateFlow(Facets())
    val facets: StateFlow<Facets> = _facets.asStateFlow()

    var currentSearch: String = ""
    var currentCategory: String = ""
    var currentGenre: String = ""
    var currentFormat: String = ""
    var currentSort: String = "added_desc"   // "Récemment ajoutés" — default library sort

    private val perPage = 60
    private var page = 1
    private var pages = 1
    private var total = 0
    private val loaded = mutableListOf<Book>()
    private var loading = false

    init { loadFacets(); loadAll() }

    fun loadAll() {
        loadBooks()
    }

    private fun isUnfiltered() =
        currentSearch.isBlank() && currentCategory.isBlank() &&
            currentGenre.isBlank() && currentFormat.isBlank()

    /** Server-wide filter facets (all categories/genres/formats, not one page's). */
    fun loadFacets() {
        viewModelScope.launch {
            runCatching { bookRepo.getFilters() }.onSuccess {
                _facets.value = Facets(it.categories, it.genres, it.formats)
            }
        }
    }

    fun setSort(sort: String) { if (sort != currentSort) loadBooks(sort = sort) }

    fun loadBooks(
        search: String = currentSearch,
        category: String = currentCategory,
        genre: String = currentGenre,
        format: String = currentFormat,
        sort: String = currentSort
    ) {
        currentSearch = search; currentCategory = category
        currentGenre = genre; currentFormat = format; currentSort = sort
        page = 1
        viewModelScope.launch { fetchPage(reset = true) }
    }

    /** Load the next page (called when the grid nears its end). */
    fun loadMore() {
        val st = _state.value
        if (loading || st !is LibraryState.Success || !st.hasMore) return
        page += 1
        viewModelScope.launch { fetchPage(reset = false) }
    }

    private suspend fun fetchPage(reset: Boolean) {
        if (loading) return
        loading = true
        if (reset && _state.value !is LibraryState.Success) _state.value = LibraryState.Loading
        runCatching {
            bookRepo.getBooks(
                search = currentSearch.takeIf { it.isNotBlank() },
                category = currentCategory.takeIf { it.isNotBlank() },
                genre = currentGenre.takeIf { it.isNotBlank() },
                format = currentFormat.takeIf { it.isNotBlank() },
                sort = currentSort, page = page, perPage = perPage
            )
        }.onSuccess { resp ->
            if (reset) loaded.clear()
            loaded.addAll(resp.books)
            pages = resp.pages; total = resp.total
            val hasMore = page < pages && resp.books.isNotEmpty()
            _state.value = LibraryState.Success(loaded.toList(), hasMore = hasMore, total = total)
            // Cumulative offline snapshot on the default unfiltered view (no 50 cap).
            if (isUnfiltered()) runCatching { downloadRepo.cacheLibrary(loaded.toList()) }
        }.onFailure { e ->
            Log.e(TAG, "fetchPage($page) failed", e)
            when {
                e is HttpException && e.code() == 401 -> _sessionExpired.emit(Unit)
                reset -> {
                    val cached = runCatching { downloadRepo.getCachedLibrary() }.getOrDefault(emptyList())
                    if (cached.isNotEmpty()) {
                        loaded.clear(); loaded.addAll(cached)
                        _state.value = LibraryState.Success(loaded.toList(), hasMore = false, total = cached.size)
                        _toast.value = "Mode hors-ligne"
                    } else {
                        _state.value = LibraryState.Error(e.toUserMessage())
                    }
                }
                else -> page -= 1   // roll back so loadMore() can retry the same page
            }
        }
        loading = false
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
