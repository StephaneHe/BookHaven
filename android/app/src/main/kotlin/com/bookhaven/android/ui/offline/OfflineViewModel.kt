package com.bookhaven.android.ui.offline

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bookhaven.android.data.db.entity.DownloadedBook
import com.bookhaven.android.data.repository.DownloadRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class OfflineViewModel @Inject constructor(
    private val downloadRepo: DownloadRepository
) : ViewModel() {

    val downloads: StateFlow<List<DownloadedBook>> = downloadRepo.downloads
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    fun delete(book: DownloadedBook) {
        viewModelScope.launch { downloadRepo.deleteDownload(book.bookId) }
    }
}
