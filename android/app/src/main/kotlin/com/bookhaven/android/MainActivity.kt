package com.bookhaven.android

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.isVisible
import androidx.navigation.fragment.NavHostFragment
import androidx.navigation.ui.setupWithNavController
import com.bookhaven.android.databinding.ActivityMainBinding
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        setSupportActionBar(binding.toolbar)

        val navHost = supportFragmentManager
            .findFragmentById(R.id.nav_host_fragment) as NavHostFragment
        val navController = navHost.navController
        binding.bottomNav.setupWithNavController(navController)

        // Hide toolbar + bottom nav on screens that don't use them
        val fullScreenDests = setOf(R.id.loginFragment, R.id.bookDetailFragment, R.id.uploadFragment)
        navController.addOnDestinationChangedListener { _, destination, _ ->
            val isMain = destination.id !in fullScreenDests
            binding.toolbar.isVisible = isMain
            binding.bottomNav.isVisible = isMain
        }
    }
}
