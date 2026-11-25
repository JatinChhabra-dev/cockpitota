package com.aurelia.ev

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Receives deterministic test-runner / companion cloud intents:
 *  - com.aurelia.ev.ACTION_OPEN_CHARGING_MODAL
 *  - com.aurelia.ev.ACTION_CLOSE_CHARGING_MODAL
 *  - com.aurelia.ev.ACTION_REMOTE_CLIMATE (float extra: temperature_c)
 */
class RemoteCommandReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        Log.i("AureliaEV", "RemoteCommandReceiver received action=$action")
        val forward = Intent(context, MainActivity::class.java).apply {
            this.action = action
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            if (intent.hasExtra("temperature_c")) {
                putExtra("temperature_c", intent.getFloatExtra("temperature_c", 21.0f))
            }
        }
        context.startActivity(forward)
    }
}
