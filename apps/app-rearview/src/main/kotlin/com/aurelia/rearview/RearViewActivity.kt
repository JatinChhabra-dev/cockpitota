package com.aurelia.rearview

import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Typeface
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView

/**
 * APP-2: Rear-view Stand-in (Spec §4 M3-FR2)
 * Full-screen safety-relevant overlay triggered when GEAR_SELECTION == REVERSE (2).
 * Must render above all other UI within 500 ms.
 */
class RearViewActivity : Activity() {

    companion object {
        private const val TAG = "AureliaRearView"
        const val ACTION_HIDE = "com.aurelia.rearview.ACTION_HIDE"
    }

    private lateinit var txtLatency: TextView

    private val hideReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (intent.action == ACTION_HIDE) {
                Log.i(TAG, "Received ACTION_HIDE — closing RearViewActivity")
                finish()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val triggerTs = intent.getLongExtra("trigger_ts_ms", System.currentTimeMillis())

        val root = FrameLayout(this).apply {
            id = R.id.rearview_root
            setBackgroundColor(Color.parseColor("#0B1120"))
        }

        // Trajectory guideline canvas (simulated rear-view camera feed)
        root.addView(GuidelinesView(this), FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.MATCH_PARENT
        ))

        // Top safety header banner
        val topBar = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#CC991B1B"))
            setPadding(28, 18, 28, 18)
            gravity = Gravity.CENTER
        }
        val banner = TextView(this).apply {
            id = R.id.txt_rearview_banner
            text = "●  ${getString(R.string.rearview_banner)}"
            setTextColor(Color.WHITE)
            textSize = 24f
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
        }
        txtLatency = TextView(this).apply {
            id = R.id.txt_rearview_latency
            text = "Measuring render latency..."
            setTextColor(Color.parseColor("#FECACA"))
            textSize = 14f
            typeface = Typeface.MONOSPACE
            gravity = Gravity.CENTER
        }
        topBar.addView(banner)
        topBar.addView(txtLatency)

        root.addView(topBar, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
            Gravity.TOP
        ))

        // Bottom warning strip
        val warning = TextView(this).apply {
            id = R.id.txt_rearview_warning
            text = getString(R.string.rearview_warning)
            setTextColor(Color.parseColor("#FDE68A"))
            setBackgroundColor(Color.parseColor("#CC0F172A"))
            textSize = 15f
            gravity = Gravity.CENTER
            setPadding(24, 16, 24, 16)
        }
        root.addView(warning, FrameLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,
            ViewGroup.LayoutParams.WRAP_CONTENT,
            Gravity.BOTTOM
        ))

        setContentView(root)
        registerReceiver(hideReceiver, IntentFilter(ACTION_HIDE), Context.RECEIVER_EXPORTED)

        // Log exact first-frame render latency for M3-FR2 / M5-FR3 (< 500 ms ceiling)
        root.post {
            val elapsedMs = (System.currentTimeMillis() - triggerTs).coerceAtLeast(1L)
            txtLatency.text = "RENDER LATENCY: ${elapsedMs} ms  (Ceiling: < 500 ms)"
            Log.i(TAG, "[RENDERED] RearViewActivity visible in ${elapsedMs}ms")
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            unregisterReceiver(hideReceiver)
        } catch (_: Exception) {
        }
    }

    private class GuidelinesView(context: Context) : View(context) {
        private val greenPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#22C55E")
            strokeWidth = 8f
            style = Paint.Style.STROKE
        }
        private val amberPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#F59E0B")
            strokeWidth = 8f
            style = Paint.Style.STROKE
        }
        private val redPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.parseColor("#EF4444")
            strokeWidth = 10f
            style = Paint.Style.STROKE
        }

        override fun onDraw(canvas: Canvas) {
            super.onDraw(canvas)
            val w = width.toFloat()
            val h = height.toFloat()

            // Trapezoid parking guidelines (far=green, mid=amber, close=red)
            canvas.drawLine(w * 0.22f, h * 0.88f, w * 0.36f, h * 0.35f, greenPaint)
            canvas.drawLine(w * 0.78f, h * 0.88f, w * 0.64f, h * 0.35f, greenPaint)
            canvas.drawLine(w * 0.36f, h * 0.35f, w * 0.64f, h * 0.35f, greenPaint)

            canvas.drawLine(w * 0.31f, h * 0.56f, w * 0.69f, h * 0.56f, amberPaint)
            canvas.drawLine(w * 0.25f, h * 0.78f, w * 0.75f, h * 0.78f, redPaint)
        }
    }
}
