package com.smartschool.card.data

import android.content.Context

class SessionManager(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    var token: String?
        get() = prefs.getString(KEY_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_TOKEN, value).apply()

    var email: String?
        get() = prefs.getString(KEY_EMAIL, null)
        set(value) = prefs.edit().putString(KEY_EMAIL, value).apply()

    var displayName: String?
        get() = prefs.getString(KEY_DISPLAY_NAME, null)
        set(value) = prefs.edit().putString(KEY_DISPLAY_NAME, value).apply()

    var cardUid: String?
        get() = prefs.getString(KEY_CARD_UID, null)
        set(value) = prefs.edit().putString(KEY_CARD_UID, value).apply()

    fun clear() {
        prefs.edit().clear().apply()
    }

    val isLoggedIn: Boolean
        get() = !token.isNullOrBlank()

    companion object {
        private const val PREFS_NAME = "smartschool_session"
        private const val KEY_TOKEN = "token"
        private const val KEY_EMAIL = "email"
        private const val KEY_DISPLAY_NAME = "display_name"
        private const val KEY_CARD_UID = "card_uid"
    }
}
