package com.smartschool.card

import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.credentials.CredentialManager
import androidx.credentials.GetCredentialRequest
import androidx.credentials.exceptions.GetCredentialException
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.google.android.libraries.identity.googleid.GetGoogleIdOption
import com.google.android.libraries.identity.googleid.GoogleIdTokenCredential
import com.smartschool.card.ui.AppViewModel
import com.smartschool.card.ui.CardScreen
import com.smartschool.card.ui.LoginScreen
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val viewModel: AppViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            val colorScheme = lightColorScheme(primary = androidx.compose.ui.graphics.Color(0xFF2563EB))
            MaterialTheme(colorScheme = colorScheme) {
                val state = viewModel.state.collectAsStateWithLifecycle().value
                val snackbarHostState = remember { SnackbarHostState() }

                LaunchedEffect(state.error, state.successMessage) {
                    state.error?.let {
                        snackbarHostState.showSnackbar(it)
                        viewModel.clearMessages()
                    }
                    state.successMessage?.let {
                        snackbarHostState.showSnackbar(it)
                        viewModel.clearMessages()
                    }
                }

                Scaffold(snackbarHost = { SnackbarHost(snackbarHostState) }) { padding ->
                    Box(modifier = Modifier.fillMaxSize().padding(padding)) {
                        if (state.isLoggedIn) {
                            CardScreen(
                                state = state,
                                onCreateCard = viewModel::createCard,
                                onLogout = viewModel::logout,
                            )
                        } else {
                            LoginScreen(
                                isLoading = state.isLoading,
                                onGoogleSignInClick = ::signInWithGoogle,
                            )
                        }
                    }
                }
            }
        }
    }

    private fun signInWithGoogle() {
        val webClientId = BuildConfig.GOOGLE_WEB_CLIENT_ID
        if (webClientId.startsWith("YOUR_GOOGLE")) {
            Toast.makeText(
                this,
                "Налаштуйте GOOGLE_WEB_CLIENT_ID у app/build.gradle.kts",
                Toast.LENGTH_LONG,
            ).show()
            return
        }

        val googleIdOption = GetGoogleIdOption.Builder()
            .setFilterByAuthorizedAccounts(false)
            .setServerClientId(webClientId)
            .build()

        val request = GetCredentialRequest.Builder()
            .addCredentialOption(googleIdOption)
            .build()

        viewModel.onGoogleSignInStarted()
        CoroutineScope(Dispatchers.Main).launch {
            try {
                val result = CredentialManager.create(this@MainActivity)
                    .getCredential(this@MainActivity, request)
                val credential = GoogleIdTokenCredential.createFrom(result.credential.data)
                viewModel.onGoogleSignInSuccess(credential.idToken)
            } catch (e: GetCredentialException) {
                viewModel.onGoogleSignInError(
                    "Google Sign-In: ${e.message ?: e.type ?: "скасовано"}",
                )
            } catch (e: Exception) {
                viewModel.onGoogleSignInError(e.message ?: e.javaClass.simpleName)
            }
        }
    }
}
