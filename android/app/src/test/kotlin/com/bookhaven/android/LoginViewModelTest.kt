package com.bookhaven.android

import com.bookhaven.android.data.api.model.LoginRequest
import com.bookhaven.android.data.api.model.LoginResponse
import com.bookhaven.android.data.repository.BookRepository
import com.bookhaven.android.ui.login.LoginState
import com.bookhaven.android.ui.login.LoginViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class LoginViewModelTest {
    @Before fun setUp() { Dispatchers.setMain(UnconfinedTestDispatcher()) }
    @After fun tearDown() { Dispatchers.resetMain() }

    @Test fun R09_loginSendsUsernameWithoutPin() {
        val api = FakeApi { c -> if (c.name == "login") LoginResponse(true, "u1", "alice") else null }
        // Blank server_url: init's checkSession() stops at NoServerUrl without network/Log.
        val prefs = fakePrefs(mapOf("server_url" to ""))
        val vm = LoginViewModel(BookRepository(api.api), prefs)
        assertEquals(LoginState.NoServerUrl, vm.state.value)

        vm.login("alice", offline = false)

        val req = api.callsTo("login").single().args.single() as LoginRequest
        assertEquals("alice", req.username)
        assertNull("no PIN is ever sent", req.pin)
        assertEquals("alice", vm.loginResult.value!!.getOrThrow())
        assertEquals("alice", prefs.getString("current_user", null))
        assertTrue("the PIN-required endpoint is never consulted", api.callsTo("pinRequired").isEmpty())
    }

    @Test fun R09_noPinStateOrApiInLoginFlow() {
        val stateNames = LoginState::class.java.declaredClasses.map { it.simpleName }
        assertTrue(stateNames.containsAll(listOf("Loading", "NoServerUrl", "LoggedIn", "Users", "Error")))
        assertTrue("no PIN state: $stateNames", stateNames.none { it.contains("pin", ignoreCase = true) })
        val vmMembers = LoginViewModel::class.java.declaredMethods.map { it.name } +
            LoginViewModel::class.java.declaredFields.map { it.name }
        assertTrue("no PIN member in LoginViewModel: $vmMembers", vmMembers.none { it.contains("pin", ignoreCase = true) })
    }
}
