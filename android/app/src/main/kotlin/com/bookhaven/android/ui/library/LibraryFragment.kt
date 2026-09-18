package com.bookhaven.android.ui.library

import android.content.Intent
import android.content.SharedPreferences
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.PopupMenu
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.os.bundleOf
import androidx.core.widget.doAfterTextChanged
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.bookhaven.android.R
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.databinding.DialogServerConfigBinding
import com.bookhaven.android.databinding.FragmentLibraryBinding
import com.bookhaven.android.di.DEFAULT_SERVER_URL
import com.bookhaven.android.ui.common.showError
import com.bookhaven.android.ui.detail.BookDetailFragment
import com.bookhaven.android.ui.reader.ReaderActivity
import com.google.android.material.chip.Chip
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import javax.inject.Inject

// Library sort options: server sort key -> French label. added_desc is default.
private val SORT_OPTIONS = listOf(
    "added_desc" to "Récemment ajoutés",
    "last_read_desc" to "Récemment lus",
    "title" to "Titre",
    "author" to "Auteur",
)

@AndroidEntryPoint
class LibraryFragment : Fragment() {

    private var _binding: FragmentLibraryBinding? = null
    private val binding get() = _binding!!
    private val vm: LibraryViewModel by activityViewModels()

    @Inject lateinit var prefs: SharedPreferences

    private lateinit var bookAdapter: BookAdapter
    private var downloadedIds = emptySet<Int>()
    private var downloadingIds = emptySet<Int>()
    private var searchJob: Job? = null

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View = FragmentLibraryBinding.inflate(inflater, container, false)
        .also { _binding = it }.root

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Books grid
        bookAdapter = BookAdapter(
            serverUrl = { prefs.getString("server_url", DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL },
            downloads = { downloadedIds },
            downloading = { downloadingIds },
            onClick = ::openBook,
            onLongClick = ::showBookMenu,
            onDownloadClick = { vm.downloadBook(it) }
        )
        binding.rvBooks.layoutManager = GridLayoutManager(requireContext(), 3)
        binding.rvBooks.adapter = bookAdapter
        // Infinite pagination: load the next page as the grid nears its end.
        binding.rvBooks.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrolled(rv: RecyclerView, dx: Int, dy: Int) {
                if (dy <= 0) return
                val lm = rv.layoutManager as GridLayoutManager
                if (lm.findLastVisibleItemPosition() >= lm.itemCount - 6) vm.loadMore()
            }
        })

        // Debounced search (300 ms) that cancels any in-flight query.
        binding.etSearch.doAfterTextChanged { text ->
            searchJob?.cancel()
            searchJob = viewLifecycleOwner.lifecycleScope.launch {
                delay(300)
                vm.loadBooks(search = text.toString())
            }
        }
        binding.btnSort.setOnClickListener { showSortMenu(it) }
        binding.btnSettings.setOnClickListener { showServerConfigDialog() }
        binding.swipeRefresh.setOnRefreshListener { vm.loadFacets(); vm.loadAll() }
        binding.fabUpload.setOnClickListener {
            findNavController().navigate(R.id.action_library_to_upload)
        }

        viewLifecycleOwner.lifecycleScope.launch {
            vm.facets.collect { f ->
                setupCategoryChips(listOf("") + f.categories)
                setupGenreChips(listOf("") + f.genres)
            }
        }

        viewLifecycleOwner.lifecycleScope.launch {
            vm.downloads.collect { list ->
                downloadedIds = list.map { it.bookId }.toSet()
                bookAdapter.notifyDataSetChanged()
            }
        }
        viewLifecycleOwner.lifecycleScope.launch {
            vm.downloading.collect { ids ->
                downloadingIds = ids
                bookAdapter.notifyDataSetChanged()
            }
        }
        viewLifecycleOwner.lifecycleScope.launch {
            vm.state.collect { state ->
                binding.swipeRefresh.isRefreshing = state is LibraryState.Loading
                when (state) {
                    is LibraryState.Loading -> Unit
                    is LibraryState.Success -> {
                        bookAdapter.submitList(state.books)
                        binding.tvEmpty.visibility = if (state.books.isEmpty()) View.VISIBLE else View.GONE
                    }
                    is LibraryState.Error ->
                        requireContext().showError(state.message)
                }
            }
        }
        viewLifecycleOwner.lifecycleScope.launch {
            vm.toast.collect { msg ->
                msg ?: return@collect
                Toast.makeText(requireContext(), msg, Toast.LENGTH_SHORT).show()
                vm.clearToast()
            }
        }
        viewLifecycleOwner.lifecycleScope.launch {
            vm.sessionExpired.collect {
                // Session expired mid-use → back to login, no error dialog. (Fix 4)
                findNavController().navigate(R.id.loginFragment)
            }
        }
    }

    private fun setupCategoryChips(categories: List<String>) {
        binding.chipGroup.removeAllViews()
        categories.forEach { cat ->
            val chip = Chip(requireContext()).apply {
                text = if (cat.isEmpty()) "Toutes" else cat
                isCheckable = true
                isChecked = cat == vm.currentCategory
                setOnClickListener {
                    vm.loadBooks(category = if (cat == vm.currentCategory) "" else cat)
                }
            }
            binding.chipGroup.addView(chip)
        }
    }

    private fun setupGenreChips(genres: List<String>) {
        binding.chipGroupGenre.removeAllViews()
        genres.forEach { g ->
            val chip = Chip(requireContext()).apply {
                text = if (g.isEmpty()) "Tous" else g
                isCheckable = true
                isChecked = g == vm.currentGenre
                setOnClickListener {
                    vm.loadBooks(genre = if (g == vm.currentGenre) "" else g)
                }
            }
            binding.chipGroupGenre.addView(chip)
        }
    }

    private fun showSortMenu(anchor: View) {
        val menu = PopupMenu(requireContext(), anchor)
        SORT_OPTIONS.forEachIndexed { i, (_, label) -> menu.menu.add(0, i, i, label) }
        menu.setOnMenuItemClickListener { item ->
            vm.setSort(SORT_OPTIONS[item.itemId].first)
            true
        }
        menu.show()
    }

    private fun openBook(book: Book) {
        // Use the downloaded copy when available so the reader works offline and avoids streaming.
        val local = vm.downloads.value.firstOrNull { it.bookId == book.id }
        startActivity(Intent(requireContext(), ReaderActivity::class.java).apply {
            putExtra(ReaderActivity.EXTRA_BOOK_ID, book.id)
            putExtra(ReaderActivity.EXTRA_FORMAT, book.format)
            putExtra(ReaderActivity.EXTRA_TITLE, book.title)
            local?.let { putExtra(ReaderActivity.EXTRA_LOCAL_PATH, it.localPath) }
        })
    }

    private fun openBookDetail(book: Book) {
        findNavController().navigate(
            R.id.action_library_to_detail,
            bundleOf(BookDetailFragment.ARG_BOOK_ID to book.id)
        )
    }

    private fun showBookMenu(book: Book) {
        val downloaded = downloadedIds.contains(book.id)
        val downloadLabel = if (downloaded) "Déjà téléchargé" else "Télécharger"
        val options = arrayOf("Lire", downloadLabel, "Détails")
        AlertDialog.Builder(requireContext())
            .setTitle(book.title)
            .setItems(options) { _, which ->
                when (which) {
                    0 -> openBook(book)
                    1 -> if (!downloaded) vm.downloadBook(book)
                    2 -> openBookDetail(book)
                }
            }
            .show()
    }

    private fun showServerConfigDialog() {
        val db = DialogServerConfigBinding.inflate(layoutInflater)
        db.etServerUrl.setText(prefs.getString("server_url", DEFAULT_SERVER_URL))
        AlertDialog.Builder(requireContext())
            .setTitle("Server URL")
            .setView(db.root)
            .setPositiveButton("Save") { _, _ ->
                prefs.edit().putString("server_url", db.etServerUrl.text.toString().trimEnd('/')).apply()
                vm.loadAll()
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroyView() { super.onDestroyView(); _binding = null }
}
