package org.tunnelgram.android

import android.content.Context

object RuntimeState {
    private const val PREFS = "runtime_state"
    private const val KEY_RUNNING = "running"
    private const val KEY_STATUS = "status"
    private const val KEY_PROFILE = "profile"

    fun update(context: Context, running: Boolean, status: String, profile: String = "") {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_RUNNING, running)
            .putString(KEY_STATUS, status)
            .putString(KEY_PROFILE, profile)
            .apply()
    }

    fun read(context: Context): State {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return State(
            running = prefs.getBoolean(KEY_RUNNING, false),
            status = prefs.getString(KEY_STATUS, "Остановлено") ?: "Остановлено",
            profile = prefs.getString(KEY_PROFILE, "") ?: "",
        )
    }

    data class State(val running: Boolean, val status: String, val profile: String)
}
