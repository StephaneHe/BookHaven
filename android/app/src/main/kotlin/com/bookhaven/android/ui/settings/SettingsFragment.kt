package com.bookhaven.android.ui.settings

import android.content.SharedPreferences
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.SeekBar
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import com.bookhaven.android.BuildConfig
import com.bookhaven.android.databinding.FragmentSettingsBinding
import com.bookhaven.android.ui.reader.ComicReaderFragment
import com.bookhaven.android.ui.reader.ComicReaderLogic
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class SettingsFragment : Fragment() {

    private var _b: FragmentSettingsBinding? = null
    private val b get() = _b!!
    private val vm: SettingsViewModel by viewModels()

    @Inject lateinit var prefs: SharedPreferences

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View = FragmentSettingsBinding.inflate(inflater, container, false)
        .also { _b = it }.root

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        b.tvVersion.text = "BookHaven v${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})"

        b.etServerUrl.setText(prefs.getString("server_url", "http://192.168.1.10:8097"))
        b.btnSave.setOnClickListener {
            val url = b.etServerUrl.text.toString().trimEnd('/')
            if (url.isEmpty()) { Toast.makeText(requireContext(), "URL required", Toast.LENGTH_SHORT).show(); return@setOnClickListener }
            prefs.edit().putString("server_url", url).apply()
            Toast.makeText(requireContext(), "Saved — restart app to reconnect.", Toast.LENGTH_SHORT).show()
        }

        b.btnScan.setOnClickListener { vm.triggerScan() }

        // Webtoon reading: chapters pre-cached ahead + optional offline download ahead.
        val k = ComicReaderLogic.precacheCount(
            prefs.getInt(ComicReaderFragment.PREF_PRECACHE, ComicReaderLogic.PRECACHE_DEFAULT))
        b.sbPrecache.max = ComicReaderLogic.PRECACHE_MAX
        b.sbPrecache.progress = k
        b.tvPrecache.text = "Chapitres préchargés : $k"
        b.sbPrecache.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar, value: Int, fromUser: Boolean) {
                b.tvPrecache.text = if (value == 0) "Chapitres préchargés : désactivé" else "Chapitres préchargés : $value"
                if (fromUser) prefs.edit().putInt(ComicReaderFragment.PREF_PRECACHE, value).apply()
            }
            override fun onStartTrackingTouch(sb: SeekBar) {}
            override fun onStopTrackingTouch(sb: SeekBar) {}
        })
        b.swDownloadAhead.isChecked = prefs.getBoolean(ComicReaderFragment.PREF_DOWNLOAD_AHEAD, false)
        b.swDownloadAhead.setOnCheckedChangeListener { _, on ->
            prefs.edit().putBoolean(ComicReaderFragment.PREF_DOWNLOAD_AHEAD, on).apply()
        }

        b.btnCreateUser.setOnClickListener {
            val et = EditText(requireContext()).apply { hint = "Username"; setPadding(48, 32, 48, 32) }
            AlertDialog.Builder(requireContext())
                .setTitle("New account")
                .setView(et)
                .setPositiveButton("Create") { _, _ ->
                    val name = et.text.toString().trim()
                    if (name.isNotEmpty()) vm.createUser(name)
                }
                .setNegativeButton("Cancel", null)
                .show()
        }

        b.btnLogout.setOnClickListener {
            prefs.edit().remove("current_user").apply()
            Toast.makeText(requireContext(), "Logged out — restart app.", Toast.LENGTH_SHORT).show()
        }

        viewLifecycleOwner.lifecycleScope.launch {
            vm.scanStatus.collect { status ->
                status ?: return@collect
                b.tvScanStatus.visibility = View.VISIBLE
                b.scanProgressBar.visibility = if (status.running && status.total > 0) View.VISIBLE else View.GONE
                if (status.running && status.total > 0) {
                    b.scanProgressBar.max = status.total
                    b.scanProgressBar.progress = status.current
                }
                b.tvScanStatus.text = status.message.ifBlank { if (status.running) "Scanning…" else "Done" }
            }
        }

        viewLifecycleOwner.lifecycleScope.launch {
            vm.toast.collect { msg ->
                msg ?: return@collect
                Toast.makeText(requireContext(), msg, Toast.LENGTH_SHORT).show()
                vm.clearToast()
            }
        }
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}
