package com.bookhaven.android.ui.login

import android.content.SharedPreferences
import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.bookhaven.android.data.api.toUserMessage
import com.bookhaven.android.data.repository.BookRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.net.URL
import javax.inject.Inject

private const val TAG = "LoginViewModel"

sealed class LoginState {
    object Loading : LoginState()
    object NoServerUrl : LoginState()
    object LoggedIn : LoginState()
    data class Users(val users: List<String>, val offline: Boolean) : LoginState()
    data class Error(val message: String) : LoginState()
}

@HiltViewModel
class LoginViewModel @Inject constructor(
    private val repo: BookRepository,
    private val prefs: SharedPreferences
) : ViewModel() {

    private val _state = MutableStateFlow<LoginState>(LoginState.Loading)
    val state: StateFlow<LoginState> = _state.asStateFlow()

    private val _loginResult = MutableStateFlow<Result<String>?>(null)
    val loginResult: StateFlow<Result<String>?> = _loginResult.asStateFlow()

    init { checkSession() }

    /**
     * Startup entry: validate the existing session before deciding what to show.
     * A 401 means "not logged in" → show the account list, never an error dialog.
     */
    fun checkSession() {
        val url = prefs.getString("server_url", "").orEmpty()
        if (url.isBlank()) {
            _state.value = LoginState.NoServerUrl
            return
        }
        if (!isValidUrl(url)) return

        val currentUser = prefs.getString("current_user", null)
        viewModelScope.launch {
            _state.value = LoginState.Loading

            // Reachability probe on a public endpoint distinguishes network-down from a 401.
            val reachable = runCatching { repo.checkVersion() }
            if (reachable.isFailure) {
                emitOfflineOrError(reachable.exceptionOrNull(), currentUser)   // Fix 3
                return@launch
            }

            // Server reachable — is the session still valid? getMe() returns null on 401.
            if (repo.getMe() != null) {
                _state.value = LoginState.LoggedIn
                return@launch
            }

            // Session gone, but login is password-less: silently recreate it. (Fix 2)
            if (currentUser != null) {
                if (repo.login(currentUser).isSuccess) {
                    _state.value = LoginState.LoggedIn
                    return@launch
                }
                // User no longer exists server-side — forget it and show the account list.
                prefs.edit().remove("current_user").apply()
            }

            // 401 with no recoverable session == "not logged in" → accounts, no error. (Fix 1)
            loadUsersOnline()
        }
    }

    /** Manual refresh / retry: re-probe the server then list accounts. */
    fun loadUsers() {
        val url = prefs.getString("server_url", "").orEmpty()
        if (url.isBlank()) {
            _state.value = LoginState.NoServerUrl
            return
        }
        if (!isValidUrl(url)) return
        viewModelScope.launch {
            _state.value = LoginState.Loading
            val reachable = runCatching { repo.checkVersion() }
            if (reachable.isFailure) {
                emitOfflineOrError(reachable.exceptionOrNull(), prefs.getString("current_user", null))
                return@launch
            }
            loadUsersOnline()
        }
    }

    private suspend fun loadUsersOnline() {
        runCatching { repo.getUsers().map { it.name } }
            .onSuccess { users ->
                cacheUsers(users)
                _state.value = LoginState.Users(users, offline = false)
            }
            .onFailure { e ->
                Log.e(TAG, "getUsers() failed", e)
                val cached = getCachedUsers()
                _state.value = if (cached.isNotEmpty())
                    LoginState.Users(cached, offline = true)
                else
                    LoginState.Error(e.toUserMessage())
            }
    }

    /** Network unreachable: fall back to cached/remembered accounts instead of an error. (Fix 3) */
    private fun emitOfflineOrError(ex: Throwable?, currentUser: String?) {
        Log.e(TAG, "Server unreachable — offline fallback", ex)
        val cached = getCachedUsers()
        _state.value = when {
            cached.isNotEmpty() -> LoginState.Users(cached, offline = true)
            currentUser != null -> LoginState.Users(listOf(currentUser), offline = true)
            else -> LoginState.Error(ex?.toUserMessage() ?: "Cannot reach server — check URL and network")
        }
    }

    private fun isValidUrl(url: String): Boolean = try {
        URL(url).toURI(); true
    } catch (e: Exception) {
        _state.value = LoginState.Error("Invalid server URL: $url")
        Log.e(TAG, "Malformed server URL: $url", e)
        false
    }

    fun login(username: String, offline: Boolean) {
        viewModelScope.launch {
            if (offline) {
                prefs.edit().putString("current_user", username).apply()
                _loginResult.value = Result.success(username)
                return@launch
            }
            repo.login(username).also { result ->
                result.onSuccess { name ->
                    prefs.edit().putString("current_user", name.ifBlank { username }).apply()
                }
                _loginResult.value = result
            }
        }
    }

    fun createUser(username: String) {
        viewModelScope.launch {
            repo.createUser(username)
                .onSuccess { loadUsers() }
                .onFailure { _state.value = LoginState.Error("Create failed: ${it.message}") }
        }
    }

    private fun cacheUsers(users: List<String>) =
        prefs.edit().putString("cached_users", users.joinToString(",")).apply()

    private fun getCachedUsers(): List<String> =
        (prefs.getString("cached_users", "") ?: "").split(",").filter { it.isNotBlank() }
}
