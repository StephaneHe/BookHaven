package com.bookhaven.android.ui.home

import android.content.Intent
import android.content.SharedPreferences
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.appcompat.app.AlertDialog
import androidx.core.os.bundleOf
import androidx.core.view.isVisible
import androidx.fragment.app.Fragment
import androidx.fragment.app.activityViewModels
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import coil.load
import com.bookhaven.android.R
import com.bookhaven.android.data.api.model.Book
import com.bookhaven.android.databinding.FragmentHomeBinding
import com.bookhaven.android.di.DEFAULT_SERVER_URL
import com.bookhaven.android.ui.detail.BookDetailFragment
import com.bookhaven.android.ui.library.ContinueReadingAdapter
import com.bookhaven.android.ui.library.LibraryViewModel
import com.bookhaven.android.ui.reader.ReaderActivity
import com.google.android.material.chip.Chip
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class HomeFragment : Fragment() {

    private var _binding: FragmentHomeBinding? = null
    private val binding get() = _binding!!
    private val vm: HomeViewModel by viewModels()
    // Partagé avec la Bibliothèque : sert à retrouver la copie locale + piloter les raccourcis Catégories.
    private val libVm: LibraryViewModel by activityViewModels()

    @Inject lateinit var prefs: SharedPreferences

    private lateinit var inProgressAdapter: ContinueReadingAdapter
    private lateinit var recentAdapter: CoverRailAdapter

    private fun serverUrl() = prefs.getString("server_url", DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View = FragmentHomeBinding.inflate(inflater, container, false)
        .also { _binding = it }.root

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        binding.tvVersion.text =
            "BookHaven v${com.bookhaven.android.BuildConfig.VERSION_NAME} (${com.bookhaven.android.BuildConfig.VERSION_CODE})"

        inProgressAdapter = ContinueReadingAdapter(
            serverUrl = ::serverUrl,
            onClick = ::openBook,
            onRemove = { vm.removeFromContinue(it) },
            onLongClick = ::showBookMenu
        )
        binding.rvInProgress.adapter = inProgressAdapter

        recentAdapter = CoverRailAdapter(
            serverUrl = ::serverUrl,
            onClick = ::openBook,
            onLongClick = ::showBookMenu
        )
        binding.rvRecent.adapter = recentAdapter

        viewLifecycleOwner.lifecycleScope.launch {
            vm.resume.collect { book ->
                binding.cardResume.isVisible = book != null
                book ?: return@collect
                binding.tvResumeTitle.text = book.title
                binding.tvResumeAuthor.text = book.author
                binding.pbResume.progress = book.progress.toInt()
                binding.ivResumeCover.load("${serverUrl()}/api/books/${book.id}/cover") {
                    crossfade(true)
                    placeholder(R.drawable.ic_book_placeholder)
                    error(R.drawable.ic_book_placeholder)
                }
                binding.btnResume.setOnClickListener { openBook(book) }
                binding.cardResume.setOnClickListener { openBook(book) }
            }
        }
        viewLifecycleOwner.lifecycleScope.launch {
            vm.inProgress.collect { list ->
                binding.tvInProgressLabel.isVisible = list.isNotEmpty()
                binding.rvInProgress.isVisible = list.isNotEmpty()
                inProgressAdapter.submitList(list)
            }
        }
        viewLifecycleOwner.lifecycleScope.launch {
            vm.recent.collect { list ->
                binding.tvRecentLabel.isVisible = list.isNotEmpty()
                binding.rvRecent.isVisible = list.isNotEmpty()
                recentAdapter.submitList(list)
            }
        }
        viewLifecycleOwner.lifecycleScope.launch {
            vm.categories.collect { cats ->
                binding.tvCategoriesLabel.isVisible = cats.isNotEmpty()
                setupCategoryChips(cats)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // Refléter toute progression faite depuis le lecteur au retour sur l'Accueil.
        vm.load()
    }

    private fun setupCategoryChips(categories: List<String>) {
        binding.chipCategories.removeAllViews()
        categories.forEach { cat ->
            val chip = Chip(requireContext()).apply {
                text = cat
                isClickable = true
                setOnClickListener {
                    // Applique le filtre sur le ViewModel partagé puis bascule vers la Bibliothèque.
                    libVm.loadBooks(category = cat)
                    findNavController().navigate(R.id.libraryFragment)
                }
            }
            binding.chipCategories.addView(chip)
        }
    }

    private fun openBook(book: Book) {
        val local = libVm.downloads.value.firstOrNull { it.bookId == book.id }
        startActivity(Intent(requireContext(), ReaderActivity::class.java).apply {
            putExtra(ReaderActivity.EXTRA_BOOK_ID, book.id)
            putExtra(ReaderActivity.EXTRA_FORMAT, book.format)
            putExtra(ReaderActivity.EXTRA_TITLE, book.title)
            local?.let { putExtra(ReaderActivity.EXTRA_LOCAL_PATH, it.localPath) }
        })
    }

    private fun showBookMenu(book: Book) {
        val options = arrayOf("Lire", "Détails")
        AlertDialog.Builder(requireContext())
            .setTitle(book.title)
            .setItems(options) { _, which ->
                when (which) {
                    0 -> openBook(book)
                    1 -> findNavController().navigate(
                        R.id.action_home_to_detail,
                        bundleOf(BookDetailFragment.ARG_BOOK_ID to book.id)
                    )
                }
            }
            .show()
    }

    override fun onDestroyView() { super.onDestroyView(); _binding = null }
}
