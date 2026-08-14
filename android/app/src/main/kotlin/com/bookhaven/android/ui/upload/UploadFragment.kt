package com.bookhaven.android.ui.upload

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import com.bookhaven.android.databinding.FragmentUploadBinding
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch

@AndroidEntryPoint
class UploadFragment : Fragment() {

    private var _b: FragmentUploadBinding? = null
    private val b get() = _b!!
    private val vm: UploadViewModel by viewModels()

    private val filePicker = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        uri ?: return@registerForActivityResult
        vm.analyzeFile(uri, requireContext())
    }

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View = FragmentUploadBinding.inflate(inflater, container, false).also { _b = it }.root

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        b.btnSelectFile.setOnClickListener {
            filePicker.launch("*/*")
        }

        viewLifecycleOwner.lifecycleScope.launch {
            vm.state.collect { state ->
                when (state) {
                    is UploadState.Idle -> {
                        b.progressBar.visibility = View.GONE
                        b.tvStatus.text = "Select a book file to upload"
                        b.layoutPreview.visibility = View.GONE
                        b.btnSelectFile.isEnabled = true
                    }
                    is UploadState.Analyzing -> {
                        b.progressBar.visibility = View.VISIBLE
                        b.tvStatus.text = "Analysing file…"
                        b.btnSelectFile.isEnabled = false
                        b.layoutPreview.visibility = View.GONE
                    }
                    is UploadState.Preview -> {
                        b.progressBar.visibility = View.GONE
                        b.tvStatus.text = "Review metadata:"
                        b.layoutPreview.visibility = View.VISIBLE
                        b.btnSelectFile.isEnabled = true
                        val a = state.analysis
                        b.etTitle.setText(a.title)
                        b.etAuthor.setText(a.author)
                        b.etCategory.setText(a.category)
                        b.etSeries.setText(a.series)
                        b.etGenre.setText(a.genre)
                        b.btnConfirm.setOnClickListener {
                            vm.confirm(
                                a,
                                b.etTitle.text.toString(),
                                b.etAuthor.text.toString(),
                                b.etCategory.text.toString(),
                                b.etSeries.text.toString(),
                                b.etGenre.text.toString()
                            )
                        }
                    }
                    is UploadState.Confirming -> {
                        b.progressBar.visibility = View.VISIBLE
                        b.tvStatus.text = "Uploading…"
                        b.layoutPreview.visibility = View.GONE
                    }
                    is UploadState.Done -> {
                        b.progressBar.visibility = View.GONE
                        Toast.makeText(requireContext(), "Upload successful!", Toast.LENGTH_LONG).show()
                        findNavController().popBackStack()
                    }
                    is UploadState.Error -> {
                        b.progressBar.visibility = View.GONE
                        b.tvStatus.text = "Error: ${state.message}"
                        b.btnSelectFile.isEnabled = true
                    }
                }
            }
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
