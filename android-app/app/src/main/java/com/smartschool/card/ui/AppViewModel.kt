package com.smartschool.card.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.smartschool.card.SmartSchoolApp
import com.smartschool.card.data.ApiException
import com.smartschool.card.data.ApiService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

data class UiState(
    val isLoading: Boolean = false,
    val isLoggedIn: Boolean = false,
    val email: String = "",
    val displayName: String = "",
    val cardUid: String? = null,
    val classGroup: String? = null,
    val passStatus: String? = null,
    val error: String? = null,
    val successMessage: String? = null,
)

class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val session = (application as SmartSchoolApp).sessionManager
    private val api = ApiService()
    private var pollJob: Job? = null

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

    private fun isClassUnassigned(classGroup: String?) =
        classGroup.isNullOrBlank() || classGroup == CLASS_UNASSIGNED



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
                // Offline — keep local data
            }
        }
    }

    fun startPass() {
        val token = session.token ?: return
        pollJob?.cancel()
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null, passStatus = null) }
            try {
                val prep = withContext(Dispatchers.IO) { api.startScanPrep(token) }
                _state.update {
                    it.copy(
                        isLoading = false,
                        passStatus = "waiting",
                        successMessage = "Прикладіть телефон до зчитувача (5 сек)",
                    )
                }
                pollPrep(prep.prep_id)
            } catch (e: ApiException) {
                if (e.code == 0) {
                    // Офлайн-відмовостійкість: Якщо немає з'єднання, не видаємо червону помилку. 
                    // HCE-емуляція продовжує працювати автономно (залежить від сумісності зчитувача).
                    _state.update { 
                        it.copy(
                            isLoading = false, 
                            passStatus = "offline",
                            successMessage = "Офлайн режим. Прикладіть телефон (зчитувач має підтримувати HCE)."
                        ) 
                    }
                } else {
                    _state.update { it.copy(isLoading = false, error = formatError(e)) }
                }
            } catch (e: Exception) {
                _state.update { it.copy(isLoading = false, error = formatError(e)) }
            }
        }
    }

    private fun pollPrep(prepId: String) {
        val token = session.token ?: return
        pollJob = viewModelScope.launch {
            repeat(10) {
                if (!isActive) return@launch
                delay(500)
                try {
                    val status = withContext(Dispatchers.IO) { api.scanPrepStatus(token, prepId) }
                    when (status.status) {
                        "used" -> {
                            _state.update {
                                it.copy(
                                    passStatus = "used",
                                    successMessage = "Прохід зафіксовано (${status.card_uid})",
                                )
                            }
                            return@launch
                        }
                        "expired" -> {
                            _state.update {
                                it.copy(passStatus = "expired", error = "Час вичерпано. Спробуйте ще раз.")
                            }
                            return@launch
                        }
                    }
                } catch (_: Exception) {
                    // keep polling
                }
            }
            _state.update {
                it.copy(passStatus = "expired", error = "Сканування не отримано")
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
        pollJob?.cancel()
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
        val DEFAULT_CLASSES = listOf("5-А", "6-А", "10-А", "10-Б", "10-В", "11-А", "11-Б", "11-В")
    }
}
