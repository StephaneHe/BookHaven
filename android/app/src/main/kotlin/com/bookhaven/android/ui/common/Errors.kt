package com.bookhaven.android.ui.common

import android.content.Context
import android.widget.Toast

/**
 * Show an error as a non-blocking Toast.
 * (Previously an AlertDialog with a copy button; the user prefers transient toasts.)
 * The [title] param is kept for source compatibility with existing call sites.
 */
fun Context.showError(message: String, title: String = "Erreur") {
    Toast.makeText(this, message, Toast.LENGTH_LONG).show()
}
