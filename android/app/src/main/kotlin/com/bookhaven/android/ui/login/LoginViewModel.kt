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
    data class Users(
        val users: List<String>,
        val offline: Boolean,
        val pinRequired: Boolean = false
    ) : LoginState()
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

            // Session gone. Try to silently recreate it — but ONLY if we can send a
            // valid-looking PIN. Blindly re-POSTing /api/auth/login with no PIN on
            // every launch is exactly what piled failed attempts onto the shared
            // VPN IP and locked out the web client. When a PIN is required and
            // we have none stored, we make NO attempt and just show the account list.
            if (currentUser != null) {
                val requiresPin = runCatching { repo.pinRequired() }.getOrDefault(false)
                val pin = storedPin()
                if (!requiresPin || pin != null) {
                    if (repo.login(currentUser, pin).isSuccess) {
                        _state.value = LoginState.LoggedIn
                        return@launch
                    }
                    // Failed: the stored PIN may be stale, or the user was deleted.
                    // Drop the PIN so we don't keep replaying a wrong one, then fall
                    // through to the account list rather than retrying in a loop.
                    prefs.edit().remove("server_pin").apply()
                }
            }

            // Not logged in → accounts, no error. (Fix 1)
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
                val requiresPin = runCatching { repo.pinRequired() }.getOrDefault(false)
                _state.value = LoginState.Users(users, offline = false, pinRequired = requiresPin)
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

    /**
     * @param pin the PIN typed on the login screen; blank falls back to the one
     *            remembered from a previous successful login.
     */
    fun login(username: String, pin: String, offline: Boolean) {
        viewModelScope.launch {
            if (offline) {
                prefs.edit().putString("current_user", username).apply()
                _loginResult.value = Result.success(username)
                return@launch
            }
            val effectivePin = pin.trim().ifEmpty { storedPin() }
            repo.login(username, effectivePin).also { result ->
                result.onSuccess { name ->
                    // Remember the working PIN so the next launch logs in silently
                    // (and never blindly retries a wrong/absent one).
                    if (!effectivePin.isNullOrBlank())
                        prefs.edit().putString("server_pin", effectivePin).apply()
                    prefs.edit().putString("current_user", name.ifBlank { username }).apply()
                    _loginResult.value = Result.success(name.ifBlank { username })
                }.onFailure { e ->
                    if (isForbidden(e)) {
                        // Wrong or missing PIN: forget it so we re-prompt, and report
                        // it clearly instead of as a generic failure.
                        prefs.edit().remove("server_pin").apply()
                        _loginResult.value = Result.failure(
                            InvalidPinException("Incorrect PIN — check the PIN and try again"))
                    } else {
                        _loginResult.value = Result.failure(e)
                    }
                }
            }
        }
    }

    fun createUser(username: String, pin: String) {
        viewModelScope.launch {
            val effectivePin = pin.trim().ifEmpty { storedPin() }
            repo.createUser(username, effectivePin)
                .onSuccess {
                    if (!effectivePin.isNullOrBlank())
                        prefs.edit().putString("server_pin", effectivePin).apply()
                    loadUsers()
                }
                .onFailure { e ->
                    _state.value = if (isForbidden(e))
                        LoginState.Error("Incorrect PIN — check the PIN and try again")
                    else
                        LoginState.Error("Create failed: ${e.message}")
                }
        }
    }

    private fun storedPin(): String? =
        prefs.getString("server_pin", null)?.takeIf { it.isNotBlank() }

    private fun isForbidden(e: Throwable): Boolean =
        e is retrofit2.HttpException && e.code() == 403

    private fun cacheUsers(users: List<String>) =
        prefs.edit().putString("cached_users", users.joinToString(",")).apply()

    private fun getCachedUsers(): List<String> =
        (prefs.getString("cached_users", "") ?: "").split(",").filter { it.isNotBlank() }
}

/** Thrown when the server rejects the PIN (HTTP 403), to drive a clear message. */
class InvalidPinException(message: String) : Exception(message)
