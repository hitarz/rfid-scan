package com.smartschool.card

import android.app.Application
import com.smartschool.card.data.SessionManager

class SmartSchoolApp : Application() {
    lateinit var sessionManager: SessionManager
        private set

    override fun onCreate() {
        super.onCreate()
        sessionManager = SessionManager(this)
    }
}
