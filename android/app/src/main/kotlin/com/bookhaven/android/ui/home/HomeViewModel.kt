package com.bookhaven.android.ui.home

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.data.repository.BookRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

private const val TAG = "HomeViewModel"

/**
 * Accueil : agrège les endpoints existants (aucun nouvel endpoint serveur) —
 * /api/continue-reading (Reprendre + rail « En cours ») et
 * /api/books?sort=added_desc (rail « Récemment ajoutés ») + /api/filters (raccourcis Catégories).
 */
@HiltViewModel
class HomeViewModel @Inject constructor(
    private val bookRepo: BookRepository
) : ViewModel() {

    // Le livre le plus récemment lu → grande carte « Reprendre ».
    private val _resume = MutableStateFlow<Book?>(null)
    val resume: StateFlow<Book?> = _resume.asStateFlow()

    // Le reste de la lecture en cours → rail horizontal « En cours ».
    private val _inProgress = MutableStateFlow<List<Book>>(emptyList())
    val inProgress: StateFlow<List<Book>> = _inProgress.asStateFlow()

    private val _recent = MutableStateFlow<List<Book>>(emptyList())
    val recent: StateFlow<List<Book>> = _recent.asStateFlow()

    private val _categories = MutableStateFlow<List<String>>(emptyList())
    val categories: StateFlow<List<String>> = _categories.asStateFlow()

    init { load() }

    fun load() {
        viewModelScope.launch {
            val continuing = bookRepo.getContinueReading()
            _resume.value = continuing.firstOrNull()
            _inProgress.value = if (continuing.size > 1) continuing.drop(1) else emptyList()
        }
        viewModelScope.launch {
            runCatching {
                bookRepo.getBooks(sort = "added_desc", page = 1, perPage = 20).books
            }.onSuccess { _recent.value = it }
                .onFailure { Log.e(TAG, "recent books failed", it) }
        }
        viewModelScope.launch {
            runCatching { bookRepo.getFilters().categories }
                .onSuccess { _categories.value = it }
                .onFailure { Log.e(TAG, "filters failed", it) }
        }
    }

    /** Retire un livre de la lecture en cours (efface la progression côté serveur). */
    fun removeFromContinue(book: Book) {
        viewModelScope.launch {
            bookRepo.deleteProgress(book.id)
            val continuing = bookRepo.getContinueReading()
            _resume.value = continuing.firstOrNull()
            _inProgress.value = if (continuing.size > 1) continuing.drop(1) else emptyList()
        }
    }
}
