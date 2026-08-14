package com.bookhaven.android.ui.reader

import android.content.SharedPreferences
import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.fragment.app.Fragment
import com.bookhaven.android.R
import com.bookhaven.android.databinding.ActivityReaderBinding
import com.bookhaven.android.di.DEFAULT_SERVER_URL
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class ReaderActivity : AppCompatActivity() {

    private lateinit var binding: ActivityReaderBinding

    @Inject lateinit var prefs: SharedPreferences

    companion object {
        const val EXTRA_BOOK_ID = "book_id"
        const val EXTRA_FORMAT = "format"
        const val EXTRA_TITLE = "title"
        const val EXTRA_LOCAL_PATH = "local_path"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityReaderBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setSupportActionBar(binding.toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)

        val bookId = intent.getIntExtra(EXTRA_BOOK_ID, -1)
        val format = intent.getStringExtra(EXTRA_FORMAT) ?: ""
        val title = intent.getStringExtra(EXTRA_TITLE) ?: ""
        val localPath = intent.getStringExtra(EXTRA_LOCAL_PATH)
        val serverUrl = prefs.getString("server_url", DEFAULT_SERVER_URL) ?: DEFAULT_SERVER_URL

        supportActionBar?.title = title

        if (savedInstanceState == null) {
            val fragment: Fragment = when (format.lowercase()) {
                "epub" -> EpubReaderFragment.newInstance(bookId, serverUrl, localPath)
                "pdf"  -> PdfReaderFragment.newInstance(bookId, serverUrl, localPath)
                "cbz", "cbr" -> ComicReaderFragment.newInstance(bookId, serverUrl, localPath)
                else   -> EpubReaderFragment.newInstance(bookId, serverUrl, localPath)
            }
            supportFragmentManager.beginTransaction()
                .replace(R.id.reader_container, fragment)
                .commit()
        }
    }

    override fun onSupportNavigateUp(): Boolean { finish(); return true }
}
