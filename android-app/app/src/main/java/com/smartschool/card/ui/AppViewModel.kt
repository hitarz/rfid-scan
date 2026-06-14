package com.smartschool.card.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.smartschool.card.SmartSchoolApp
import com.smartschool.card.data.ApiException
import com.smartschool.card.data.ApiService
import com.smartschool.card.nfc.HceScanEvents
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.LocalTime
import java.time.format.DateTimeFormatter

data class UiState(
    val isLoading: Boolean = false,
    val isLoggedIn: Boolean = false,
    val email: String = "",
    val displayName: String = "",
    val cardUid: String? = null,
    val classGroup: String? = null,
    // null = не сканувалось, інакше час останнього сканування у форматі "HH:mm"
    val lastScanTime: String? = null,
    val error: String? = null,
    val successMessage: String? = null,
)

class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val session = (application as SmartSchoolApp).sessionManager
    private val api = ApiService()

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()

    init {
        if (session.isLoggedIn) {
            _state.update {
                it.copy(
                    isLoggedIn = true,
                    email = session.email.orEmpty(),
                    displayName = session.displayName.orEmpty(),
                    cardUid = session.cardUid,
                )
            }
            refreshProfile()
        }

        // Слухаємо події успішного HCE-сканування від CardEmulationService
        viewModelScope.launch {
            HceScanEvents.flow.collect { cardUid ->
                val timeStr = LocalTime.now().format(DateTimeFormatter.ofPattern("HH:mm"))
                _state.update {
                    it.copy(lastScanTime = timeStr)
                }
            }
        }
    }

    fun clearMessages() {
        _state.update { it.copy(error = null, successMessage = null) }
    }

    private fun formatError(e: Exception): String {
        return when (e) {
            is ApiException -> e.message ?: "Помилка сервера (${e.code})"
            else -> e.message?.takeIf { it.isNotBlank() }
                ?: e.javaClass.simpleName
                ?: "Невідома помилка"
        }
    }

    fun onGoogleSignInStarted() {
        _state.update { it.copy(isLoading = true, error = null) }
    }

    fun onGoogleSignInSuccess(idToken: String) {
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            try {
                val response = withContext(Dispatchers.IO) { api.authGoogle(idToken) }
                session.token = response.token
                session.email = response.email
                session.displayName = response.display_name
                session.cardUid = response.card_uid
                _state.update {
                    it.copy(
                        isLoading = false,
                        isLoggedIn = true,
                        email = response.email,
                        displayName = response.display_name,
                        cardUid = response.card_uid,
                        classGroup = response.class_group,
                        successMessage = "Вхід виконано",
                    )
                }
            } catch (e: Exception) {
                _state.update { it.copy(isLoading = false, error = formatError(e)) }
            }
        }
    }

    fun onGoogleSignInError(message: String) {
        _state.update { it.copy(isLoading = false, error = message) }
    }

    fun refreshProfile() {
        val token = session.token ?: return
        viewModelScope.launch {
            try {
                val me = withContext(Dispatchers.IO) { api.getMe(token) }
                session.cardUid = me.card_uid
                _state.update {
                    it.copy(
                        email = me.email,
                        displayName = me.display_name,
                        cardUid = me.card_uid,
                        classGroup = me.class_group,
                    )
                }
            } catch (_: Exception) {
                // Offline — зберігаємо локальні дані
            }
        }
    }

    fun createCard() {
        val token = session.token ?: return
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            try {
                val response = withContext(Dispatchers.IO) { api.createCard(token) }
                session.cardUid = response.card_uid
                _state.update {
                    it.copy(
                        isLoading = false,
                        cardUid = response.card_uid,
                        classGroup = response.class_group,
                        successMessage = "Картку створено: ${response.card_uid}",
                    )
                }
            } catch (e: Exception) {
                _state.update { it.copy(isLoading = false, error = formatError(e)) }
            }
        }
    }

    fun logout() {
        val token = session.token
        viewModelScope.launch {
            if (token != null) {
                withContext(Dispatchers.IO) {
                    runCatching { api.logout(token) }
                }
            }
            session.clear()
            _state.value = UiState()
        }
    }

    companion object {
        const val CLASS_UNASSIGNED = "Не задано"
    }
}
