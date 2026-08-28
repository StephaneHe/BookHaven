package com.bookhaven.android.ui.login

import android.content.SharedPreferences
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AlertDialog
import androidx.fragment.app.Fragment
import androidx.fragment.app.viewModels
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.bookhaven.android.R
import com.bookhaven.android.databinding.FragmentLoginBinding
import com.bookhaven.android.ui.common.showError
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class LoginFragment : Fragment() {

    private var _b: FragmentLoginBinding? = null
    private val b get() = _b!!
    private val vm: LoginViewModel by viewModels()
    private var isOffline = false

    @Inject lateinit var prefs: SharedPreferences

    override fun onCreateView(
        inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?
    ): View = FragmentLoginBinding.inflate(inflater, container, false).also { _b = it }.root

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        // Session validity is checked asynchronously in the ViewModel (LoginState.LoggedIn),
        // so we never trust a stale current_user pref without confirming the session.

        b.btnRefresh.setOnClickListener { vm.loadUsers() }
        b.btnCreateUser.setOnClickListener { showCreateUserDialog() }

        b.btnConfigureServer.setOnClickListener { showServerConfigDialog() }

        viewLifecycleOwner.lifecycleScope.launch {
            vm.state.collect { state ->
                b.layoutNoServer.visibility = View.GONE
                when (state) {
                    is LoginState.Loading -> {
                        b.progressBar.visibility = View.VISIBLE
                        b.tvOfflineBadge.visibility = View.GONE
                        b.rvUsers.visibility = View.GONE
                    }
                    is LoginState.NoServerUrl -> {
                        b.progressBar.visibility = View.GONE
                        b.tvOfflineBadge.visibility = View.GONE
                        b.rvUsers.visibility = View.GONE
                        b.layoutNoServer.visibility = View.VISIBLE
                    }
                    is LoginState.LoggedIn -> {
                        b.progressBar.visibility = View.VISIBLE
                        findNavController().navigate(R.id.action_login_to_main)
                    }
                    is LoginState.Users -> {
                        b.progressBar.visibility = View.GONE
                        isOffline = state.offline
                        b.tvOfflineBadge.visibility = if (state.offline) View.VISIBLE else View.GONE
                        val showPin = state.pinRequired && !state.offline
                        b.etPin.visibility = if (showPin) View.VISIBLE else View.GONE
                        b.tvPinHint.visibility = if (showPin) View.VISIBLE else View.GONE
                        b.rvUsers.visibility = View.VISIBLE
                        b.rvUsers.layoutManager = LinearLayoutManager(requireContext())
                        b.rvUsers.adapter = UserAdapter(state.users) {
                            vm.login(it, b.etPin.text?.toString().orEmpty(), isOffline)
                        }
                    }
                    is LoginState.Error -> {
                        b.progressBar.visibility = View.GONE
                        requireContext().showError(state.message)
                    }
                }
            }
        }

        viewLifecycleOwner.lifecycleScope.launch {
            vm.loginResult.collect { result ->
                result ?: return@collect
                result.onSuccess { findNavController().navigate(R.id.action_login_to_main) }
                    .onFailure {
                        val msg = if (it is InvalidPinException) it.message.orEmpty()
                                  else "Login failed: ${it.message}"
                        requireContext().showError(msg)
                    }
            }
        }
    }

    private fun showServerConfigDialog() {
        val et = EditText(requireContext()).apply {
            hint = "http://192.168.x.x:8097"
            setText(prefs.getString("server_url", "http://192.168.1.10:8097"))
            setPadding(48, 32, 48, 32)
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
        }
        AlertDialog.Builder(requireContext())
            .setTitle("Server configuration")
            .setView(et)
            .setPositiveButton("Connect") { _, _ ->
                val url = et.text.toString().trim().trimEnd('/')
                if (url.isNotEmpty()) {
                    prefs.edit().putString("server_url", url).apply()
                    vm.loadUsers()
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun showCreateUserDialog() {
        val et = EditText(requireContext()).apply {
            hint = "Username"
            setPadding(48, 32, 48, 32)
        }
        AlertDialog.Builder(requireContext())
            .setTitle("New account")
            .setView(et)
            .setPositiveButton("Create") { _, _ ->
                val name = et.text.toString().trim()
                if (name.isNotEmpty()) vm.createUser(name, b.etPin.text?.toString().orEmpty())
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    override fun onDestroyView() { super.onDestroyView(); _b = null }
}

private class UserAdapter(
    private val users: List<String>,
    private val onClick: (String) -> Unit
) : RecyclerView.Adapter<UserAdapter.VH>() {

    class VH(val tv: TextView) : RecyclerView.ViewHolder(tv)

    override fun getItemCount() = users.size

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
        val tv = TextView(parent.context).apply {
            textSize = 18f
            setPadding(56, 40, 56, 40)
            val typedValue = android.util.TypedValue()
            parent.context.theme.resolveAttribute(android.R.attr.selectableItemBackground, typedValue, true)
            setBackgroundResource(typedValue.resourceId)
        }
        return VH(tv)
    }

    override fun onBindViewHolder(h: VH, pos: Int) {
        h.tv.text = users[pos]
        h.itemView.setOnClickListener { onClick(users[pos]) }
    }
}
