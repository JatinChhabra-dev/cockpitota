package com.aurelia.ev

import android.app.Activity
import android.app.AlertDialog
import android.car.Car
import android.car.drivingstate.CarUxRestrictions
import android.car.drivingstate.CarUxRestrictionsManager
import android.car.hardware.CarPropertyValue
import android.car.hardware.property.CarPropertyManager
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import kotlin.math.roundToInt

/**
 * APP-1: Aurelia EV & Vehicle Control (Spec §4 M3-FR1..M3-FR5)
 *
 * Binds directly to Android Automotive OS CarPropertyManager and CarUxRestrictionsManager:
 *  - PERF_VEHICLE_SPEED (291504647)         -> live digital speedometer
 *  - GEAR_SELECTION (289408000)             -> P / R / N / D gear badge + APP-2 handoff
 *  - EV_BATTERY_LEVEL (291504905)           -> battery SoC % & Wh gauge
 *  - EV_CHARGE_PORT_OPEN (287310602)        -> charge port flap state
 *  - EV_CHARGE_PORT_CONNECTED (287310603)   -> charging cable state
 *  - HVAC_TEMPERATURE_SET (358614275)       -> driver cabin climate setpoint
 *  - INFO_FUEL_TYPE (289472773)             -> EV vs Fuel powertrain identification
 */
class MainActivity : Activity() {

    companion object {
        private const val TAG = "AureliaEV"

        // AOSP VHAL Property IDs (Spec Appendix A)
        private const val PROP_PERF_VEHICLE_SPEED = 291504647
        private const val PROP_GEAR_SELECTION = 289408000
        private const val PROP_EV_BATTERY_LEVEL = 291504905
        private const val PROP_EV_CHARGE_PORT_OPEN = 287310602
        private const val PROP_EV_CHARGE_PORT_CONNECTED = 287310603
        private const val PROP_HVAC_TEMPERATURE_SET = 358614275
        private const val PROP_INFO_FUEL_TYPE = 289472773

        private const val GEAR_NEUTRAL = 1
        private const val GEAR_REVERSE = 2
        private const val GEAR_PARK = 4
        private const val GEAR_DRIVE = 8

        private const val FUEL_TYPE_ELECTRIC = 10
        private const val BATTERY_CAPACITY_WH = 75000.0f

        const val ACTION_OPEN_CHARGING_MODAL = "com.aurelia.ev.ACTION_OPEN_CHARGING_MODAL"
        const val ACTION_CLOSE_CHARGING_MODAL = "com.aurelia.ev.ACTION_CLOSE_CHARGING_MODAL"
        const val ACTION_REMOTE_CLIMATE = "com.aurelia.ev.ACTION_REMOTE_CLIMATE"
        const val ACTION_REARVIEW_SHOW = "com.aurelia.rearview.ACTION_SHOW"
        const val ACTION_REARVIEW_HIDE = "com.aurelia.rearview.ACTION_HIDE"
    }

    private var car: Car? = null
    private var carPropertyManager: CarPropertyManager? = null
    private var uxRestrictionsManager: CarUxRestrictionsManager? = null
    private val mainHandler = Handler(Looper.getMainLooper())

    // UI references
    private lateinit var txtSpeedValue: TextView
    private lateinit var txtSpeedMph: TextView
    private lateinit var txtGearValue: TextView
    private lateinit var txtPowertrainBadge: TextView
    private lateinit var txtSocValue: TextView
    private lateinit var txtSocWh: TextView
    private lateinit var progressBattery: ProgressBar
    private lateinit var txtChargePortStatus: TextView
    private lateinit var txtChargeCableStatus: TextView
    private lateinit var txtHvacTemp: TextView
    private lateinit var bannerUxRestricted: TextView
    private lateinit var bannerEuConsent: TextView
    private lateinit var btnOpenChargingModal: Button
    private lateinit var inputChargeNote: EditText

    private var chargingDialog: AlertDialog? = null
    private var isChargingModalOpen: Boolean = false
    private var currentGear: Int = GEAR_PARK
    private var currentSpeedMs: Float = 0.0f
    private var uxRestricted: Boolean = false

    private val propertyCallback = object : CarPropertyManager.CarPropertyEventCallback {
        override fun onChangeEvent(value: CarPropertyValue<*>) {
            mainHandler.post { handlePropertyUpdate(value) }
        }

        override fun onErrorEvent(propId: Int, zone: Int) {
            Log.w(TAG, "VHAL property error: propId=$propId zone=$zone")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        buildUi()
        connectCarApi()
        handleIntentAction(intent)
        Log.i(TAG, "Started APP-1 Aurelia EV release=${BuildVariantConfig.RELEASE_TAG} portrait=${isPortraitLayout()}")
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleIntentAction(intent)
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            carPropertyManager?.unregisterCallback(propertyCallback)
            uxRestrictionsManager?.unregisterListener()
            car?.disconnect()
        } catch (e: Exception) {
            Log.w(TAG, "Error disconnecting Car API: ${e.message}")
        }
    }

    private fun isPortraitLayout(): Boolean {
        val dm = resources.displayMetrics
        return dm.heightPixels > dm.widthPixels
    }

    private fun readSystemProp(key: String, defaultVal: String = ""): String {
        return try {
            val cls = Class.forName("android.os.SystemProperties")
            val method = cls.getMethod("get", String::class.java, String::class.java)
            method.invoke(null, key, defaultVal) as? String ?: defaultVal
        } catch (_: Exception) {
            defaultVal
        }
    }

    private fun handleIntentAction(intent: Intent?) {
        when (intent?.action) {
            ACTION_OPEN_CHARGING_MODAL -> openChargingScheduleModal()
            ACTION_CLOSE_CHARGING_MODAL -> closeChargingScheduleModal()
            ACTION_REMOTE_CLIMATE -> {
                val temp = intent.getFloatExtra("temperature_c", 21.0f)
                updateHvacDisplay(temp)
            }
        }
    }

    private fun connectCarApi() {
        try {
            car = Car.createCar(this)
            carPropertyManager = car?.getCarManager(Car.PROPERTY_SERVICE) as? CarPropertyManager
            uxRestrictionsManager = car?.getCarManager(Car.CAR_UX_RESTRICTION_SERVICE) as? CarUxRestrictionsManager

            carPropertyManager?.let { pm ->
                val continuousProps = listOf(PROP_PERF_VEHICLE_SPEED)
                val onChangeProps = listOf(
                    PROP_GEAR_SELECTION,
                    PROP_EV_BATTERY_LEVEL,
                    PROP_EV_CHARGE_PORT_OPEN,
                    PROP_EV_CHARGE_PORT_CONNECTED,
                    PROP_HVAC_TEMPERATURE_SET
                )
                for (p in continuousProps) {
                    try {
                        pm.registerCallback(propertyCallback, p, CarPropertyManager.SENSOR_RATE_UI)
                    } catch (e: Exception) {
                        Log.w(TAG, "Could not register continuous prop $p: ${e.message}")
                    }
                }
                for (p in onChangeProps) {
                    try {
                        pm.registerCallback(propertyCallback, p, CarPropertyManager.SENSOR_RATE_ONCHANGE)
                    } catch (e: Exception) {
                        Log.w(TAG, "Could not register onChange prop $p: ${e.message}")
                    }
                }
                readInitialProperties(pm)
            }

            uxRestrictionsManager?.let { uxm ->
                uxm.registerListener { restrictions ->
                    mainHandler.post { applyUxRestrictions(restrictions) }
                }
                uxm.currentCarUxRestrictions?.let { applyUxRestrictions(it) }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to connect Car API: ${e.message}", e)
        }
    }

    private fun readInitialProperties(pm: CarPropertyManager) {
        // Identify EV vs Fuel powertrain directly from VHAL INFO_FUEL_TYPE
        try {
            val fuelProp = pm.getProperty<Array<Int>>(PROP_INFO_FUEL_TYPE, 0)
            val types = fuelProp?.value?.toList() ?: emptyList()
            val label = when {
                types.contains(FUEL_TYPE_ELECTRIC) && types.size > 1 -> "PHEV (HYBRID)"
                types.contains(FUEL_TYPE_ELECTRIC) -> "BEV (ELECTRIC)"
                types.isNotEmpty() -> "ICE (FUEL)"
                else -> "BEV (ELECTRIC)"
            }
            txtPowertrainBadge.text = label
            Log.i(TAG, "Detected powertrain from VHAL INFO_FUEL_TYPE=$types -> $label")
        } catch (_: Exception) {
            txtPowertrainBadge.text = "BEV (ELECTRIC)"
        }

        // Initial snapshots
        listOf(
            PROP_PERF_VEHICLE_SPEED to 0,
            PROP_GEAR_SELECTION to 0,
            PROP_EV_BATTERY_LEVEL to 0,
            PROP_EV_CHARGE_PORT_OPEN to 0,
            PROP_EV_CHARGE_PORT_CONNECTED to 0,
            PROP_HVAC_TEMPERATURE_SET to 1
        ).forEach { (propId, area) ->
            try {
                val v = pm.getProperty<Any>(propId, area)
                if (v != null) handlePropertyUpdate(v)
            } catch (_: Exception) {
            }
        }
    }

    private fun handlePropertyUpdate(prop: CarPropertyValue<*>) {
        when (prop.propertyId) {
            PROP_PERF_VEHICLE_SPEED -> {
                val ms = (prop.value as? Number)?.toFloat() ?: 0f
                currentSpeedMs = ms
                val kmh = (ms * 3.6f).roundToInt()
                val mph = (ms * 2.23694f).roundToInt()
                txtSpeedValue.text = "$kmh"
                txtSpeedMph.text = "$mph MPH"
                // Enforce driving distraction lock if moving (speed > 0.5 m/s)
                updateUxLockUi(uxRestricted || ms > 0.5f)
            }

            PROP_GEAR_SELECTION -> {
                val gear = (prop.value as? Number)?.toInt() ?: GEAR_PARK
                val prevGear = currentGear
                currentGear = gear
                txtGearValue.text = when (gear) {
                    GEAR_PARK -> "P · PARK"
                    GEAR_REVERSE -> "R · REVERSE"
                    GEAR_NEUTRAL -> "N · NEUTRAL"
                    GEAR_DRIVE -> "D · DRIVE"
                    else -> "GEAR $gear"
                }
                txtGearValue.setTextColor(
                    if (gear == GEAR_REVERSE) Color.parseColor("#F87171")
                    else Color.parseColor("#60A5FA")
                )
                if (gear == GEAR_REVERSE && prevGear != GEAR_REVERSE) {
                    onReverseGearSelected()
                } else if (gear != GEAR_REVERSE && prevGear == GEAR_REVERSE) {
                    sendBroadcast(Intent(ACTION_REARVIEW_HIDE))
                }
            }

            PROP_EV_BATTERY_LEVEL -> {
                val wh = (prop.value as? Number)?.toFloat() ?: 0f
                val pct = ((wh / BATTERY_CAPACITY_WH) * 100f).roundToInt().coerceIn(0, 100)
                txtSocValue.text = "$pct%"
                txtSocWh.text = "${wh.roundToInt()} Wh"
                progressBattery.progress = pct
            }

            PROP_EV_CHARGE_PORT_OPEN -> {
                val open = (prop.value as? Boolean) == true || ((prop.value as? Number)?.toInt() ?: 0) == 1
                txtChargePortStatus.text = if (open) "PORT: OPEN" else "PORT: CLOSED"
                txtChargePortStatus.setTextColor(if (open) Color.parseColor("#38BDF8") else Color.parseColor("#94A3B8"))
            }

            PROP_EV_CHARGE_PORT_CONNECTED -> {
                val connected = (prop.value as? Boolean) == true || ((prop.value as? Number)?.toInt() ?: 0) == 1
                txtChargeCableStatus.text = if (connected) "CABLE: CONNECTED" else "CABLE: UNPLUGGED"
                txtChargeCableStatus.setTextColor(if (connected) Color.parseColor("#34D399") else Color.parseColor("#94A3B8"))
            }

            PROP_HVAC_TEMPERATURE_SET -> {
                val temp = (prop.value as? Number)?.toFloat() ?: 21.5f
                updateHvacDisplay(temp)
            }
        }
    }

    private fun updateHvacDisplay(tempC: Float) {
        txtHvacTemp.text = String.format("%.1f °C", tempC)
    }

    /**
     * Safety-critical handoff when GEAR_SELECTION transitions to REVERSE.
     *
     * Spec M3-FR4 (Planted Defect in v1.1 ONLY):
     *   On portrait layout (VAR-B), if the charging schedule modal is open,
     *   v1.1 retains modal focus and suppresses APP-2 Rear-view stand-in.
     * Spec M3-FR2 / M3-FR5 (v1.0 and v1.1-fix):
     *   Always dismisses modal cleanly and yields top z-order to APP-2 within < 500 ms.
     */
    private fun onReverseGearSelected() {
        val portrait = isPortraitLayout()
        if (BuildVariantConfig.PLANTED_DEFECT_PORTRAIT_MODAL && portrait && isChargingModalOpen) {
            Log.e(
                TAG,
                "[DEFECT_M3_FR4] Portrait charging modal retained focus; suppressed APP-2 RearView overlay " +
                    "(release=${BuildVariantConfig.RELEASE_TAG}, layout=portrait, modal=open)"
            )
            // Keep charging modal on top and suppress APP-2 handoff
            chargingDialog?.window?.decorView?.requestFocus()
            return
        }

        // Clean behavior (v1.0, v1.1-fix, and landscape variants): dismiss modal & launch APP-2 immediately
        if (isChargingModalOpen) {
            closeChargingScheduleModal()
        }
        try {
            val rvIntent = Intent(ACTION_REARVIEW_SHOW).apply {
                setClassName("com.aurelia.rearview", "com.aurelia.rearview.RearViewActivity")
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT or Intent.FLAG_ACTIVITY_SINGLE_TOP)
                putExtra("trigger_ts_ms", System.currentTimeMillis())
            }
            startActivity(rvIntent)
            Log.i(TAG, "Triggered APP-2 RearViewActivity cleanly (release=${BuildVariantConfig.RELEASE_TAG})")
        } catch (e: Exception) {
            Log.w(TAG, "APP-2 RearViewActivity not installed or unreachable: ${e.message}")
        }
    }

    private fun applyUxRestrictions(restrictions: CarUxRestrictions) {
        val active = restrictions.isRequiresDistractionOptimization ||
            (restrictions.activeRestrictions and CarUxRestrictions.UX_RESTRICTIONS_NO_KEYBOARD) != 0
        uxRestricted = active
        updateUxLockUi(active || currentSpeedMs > 0.5f)
    }

    private fun updateUxLockUi(locked: Boolean) {
        bannerUxRestricted.visibility = if (locked) View.VISIBLE else View.GONE
        btnOpenChargingModal.isEnabled = !locked
        btnOpenChargingModal.alpha = if (locked) 0.45f else 1.0f
        inputChargeNote.isEnabled = !locked
        inputChargeNote.isFocusable = !locked
        inputChargeNote.isFocusableInTouchMode = !locked
    }

    private fun openChargingScheduleModal() {
        if (isChargingModalOpen) return
        val content = LinearLayout(this).apply {
            id = R.id.modal_charging_schedule
            orientation = LinearLayout.VERTICAL
            setPadding(40, 32, 40, 32)
            setBackgroundColor(Color.parseColor("#0F172A"))
        }
        val title = TextView(this).apply {
            text = getString(R.string.modal_title)
            setTextColor(Color.WHITE)
            textSize = 22f
            typeface = Typeface.DEFAULT_BOLD
        }
        val body = TextView(this).apply {
            text = "Target SoC: 80%  |  Off-Peak Window: 23:00 – 06:00\nPre-conditioning: Enabled"
            setTextColor(Color.parseColor("#CBD5E1"))
            textSize = 16f
            setPadding(0, 16, 0, 24)
        }
        val btnClose = Button(this).apply {
            id = R.id.btn_close_charging_modal
            text = getString(R.string.modal_close)
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#2E74C9"))
            setOnClickListener { closeChargingScheduleModal() }
        }
        content.addView(title)
        content.addView(body)
        content.addView(btnClose)

        chargingDialog = AlertDialog.Builder(this)
            .setView(content)
            .setCancelable(true)
            .setOnDismissListener { isChargingModalOpen = false }
            .create()
        chargingDialog?.show()
        isChargingModalOpen = true
        Log.i(TAG, "Charging schedule modal OPENED (portrait=${isPortraitLayout()})")
    }

    private fun closeChargingScheduleModal() {
        try {
            chargingDialog?.dismiss()
        } catch (_: Exception) {
        }
        chargingDialog = null
        isChargingModalOpen = false
        Log.i(TAG, "Charging schedule modal CLOSED")
    }

    // -----------------------------------------------------------------------
    // Programmatic Ferfier / Aurelia Automotive HMI Layout
    // -----------------------------------------------------------------------
    private fun cardBg(borderColor: String = "#1E3A5F", bgColor: String = "#111B33"): GradientDrawable {
        return GradientDrawable().apply {
            setColor(Color.parseColor(bgColor))
            cornerRadius = 18f
            setStroke(2, Color.parseColor(borderColor))
        }
    }

    private fun buildUi() {
        val scroll = ScrollView(this).apply {
            setBackgroundColor(Color.parseColor("#0A0F1D"))
            isFillViewport = true
        }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(36, 28, 36, 28)
        }

        // Top Disclaimer Banner (Spec §1, §10)
        val disclaimer = TextView(this).apply {
            id = R.id.txt_disclaimer
            text = getString(R.string.disclaimer)
            setTextColor(Color.parseColor("#BFDBFE"))
            setBackgroundColor(Color.parseColor("#13294C"))
            textSize = 13f
            gravity = Gravity.CENTER
            setPadding(16, 10, 16, 10)
        }
        root.addView(disclaimer, lpMatchWrap(bottom = 18))

        // Header row
        val headerRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        val headerTitle = TextView(this).apply {
            id = R.id.txt_header_title
            text = getString(R.string.header_title)
            setTextColor(Color.WHITE)
            textSize = 26f
            typeface = Typeface.DEFAULT_BOLD
        }
        val versionBadge = TextView(this).apply {
            id = R.id.txt_version_badge
            text = "  ${BuildVariantConfig.RELEASE_TAG}  "
            setTextColor(Color.parseColor("#93C5FD"))
            textSize = 14f
            typeface = Typeface.MONOSPACE
            background = cardBg("#2E74C9", "#172554")
            setPadding(12, 6, 12, 6)
        }
        txtPowertrainBadge = TextView(this).apply {
            id = R.id.txt_powertrain_badge
            text = "BEV (ELECTRIC)"
            setTextColor(Color.parseColor("#34D399"))
            textSize = 13f
            typeface = Typeface.MONOSPACE
            background = cardBg("#065F46", "#022C22")
            setPadding(12, 6, 12, 6)
        }
        headerRow.addView(headerTitle, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        headerRow.addView(txtPowertrainBadge, lpWrap(right = 12))
        headerRow.addView(versionBadge, lpWrap())
        root.addView(headerRow, lpMatchWrap(bottom = 16))

        // UX Restriction Banner (hidden when parked)
        bannerUxRestricted = TextView(this).apply {
            id = R.id.banner_ux_restricted
            text = "⚠  ${getString(R.string.ux_locked)}"
            setTextColor(Color.parseColor("#FDE68A"))
            textSize = 15f
            typeface = Typeface.DEFAULT_BOLD
            background = cardBg("#D97706", "#451A03")
            setPadding(20, 14, 20, 14)
            visibility = View.GONE
        }
        root.addView(bannerUxRestricted, lpMatchWrap(bottom = 14))

        // EU Data Consent Banner (shown on VAR-C when debug.cora.eu_data_consent_prompt=on)
        val euConsentOn = readSystemProp("debug.cora.eu_data_consent_prompt", "off") == "on"
        bannerEuConsent = TextView(this).apply {
            id = R.id.banner_eu_consent
            text = "🇪🇺  ${getString(R.string.eu_consent)}"
            setTextColor(Color.parseColor("#93C5FD"))
            textSize = 14f
            background = cardBg("#2E74C9", "#172554")
            setPadding(20, 12, 20, 12)
            visibility = if (euConsentOn) View.VISIBLE else View.GONE
        }
        root.addView(bannerEuConsent, lpMatchWrap(bottom = 16))

        // Telemetry Row: Speedometer + Battery SoC
        val telemetryRow = LinearLayout(this).apply {
            orientation = if (isPortraitLayout()) LinearLayout.VERTICAL else LinearLayout.HORIZONTAL
        }

        // Speed & Gear Card
        val speedCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = cardBg("#2E74C9", "#0F172A")
            setPadding(28, 22, 28, 22)
        }
        val speedLabel = TextView(this).apply {
            text = "VEHICLE SPEED & GEAR"
            setTextColor(Color.parseColor("#94A3B8"))
            textSize = 12f
            typeface = Typeface.MONOSPACE
        }
        txtSpeedValue = TextView(this).apply {
            id = R.id.txt_speed_value
            text = "0"
            setTextColor(Color.parseColor("#34D399"))
            textSize = 54f
            typeface = Typeface.DEFAULT_BOLD
        }
        val speedSubRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        val speedUnit = TextView(this).apply {
            text = "${getString(R.string.speed_unit)}   |   "
            setTextColor(Color.parseColor("#94A3B8"))
            textSize = 16f
        }
        txtSpeedMph = TextView(this).apply {
            id = R.id.txt_speed_mph
            text = "0 MPH"
            setTextColor(Color.parseColor("#CBD5E1"))
            textSize = 16f
            typeface = Typeface.MONOSPACE
        }
        speedSubRow.addView(speedUnit)
        speedSubRow.addView(txtSpeedMph)

        txtGearValue = TextView(this).apply {
            id = R.id.txt_gear_value
            text = "P · PARK"
            setTextColor(Color.parseColor("#60A5FA"))
            textSize = 20f
            typeface = Typeface.DEFAULT_BOLD
            setPadding(0, 14, 0, 0)
        }
        speedCard.addView(speedLabel)
        speedCard.addView(txtSpeedValue)
        speedCard.addView(speedSubRow)
        speedCard.addView(txtGearValue)

        // EV Battery & Charging Card
        val batteryCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = cardBg("#0E7490", "#0F172A")
            setPadding(28, 22, 28, 22)
        }
        val batLabel = TextView(this).apply {
            text = "TRACTION BATTERY & CHARGE PORT"
            setTextColor(Color.parseColor("#94A3B8"))
            textSize = 12f
            typeface = Typeface.MONOSPACE
        }
        txtSocValue = TextView(this).apply {
            id = R.id.txt_soc_value
            text = "80%"
            setTextColor(Color.parseColor("#38BDF8"))
            textSize = 48f
            typeface = Typeface.DEFAULT_BOLD
        }
        txtSocWh = TextView(this).apply {
            id = R.id.txt_soc_wh
            text = "60000 Wh"
            setTextColor(Color.parseColor("#94A3B8"))
            textSize = 14f
            typeface = Typeface.MONOSPACE
        }
        progressBattery = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply {
            id = R.id.progress_battery
            max = 100
            progress = 80
        }
        txtChargePortStatus = TextView(this).apply {
            id = R.id.txt_charge_port_status
            text = "PORT: CLOSED"
            setTextColor(Color.parseColor("#94A3B8"))
            textSize = 14f
            typeface = Typeface.MONOSPACE
            setPadding(0, 12, 0, 4)
        }
        txtChargeCableStatus = TextView(this).apply {
            id = R.id.txt_charge_cable_status
            text = "CABLE: UNPLUGGED"
            setTextColor(Color.parseColor("#94A3B8"))
            textSize = 14f
            typeface = Typeface.MONOSPACE
        }
        batteryCard.addView(batLabel)
        batteryCard.addView(txtSocValue)
        batteryCard.addView(txtSocWh)
        batteryCard.addView(progressBattery, lpMatchWrap(top = 8, bottom = 6))
        batteryCard.addView(txtChargePortStatus)
        batteryCard.addView(txtChargeCableStatus)

        if (isPortraitLayout()) {
            telemetryRow.addView(speedCard, lpMatchWrap(bottom = 16))
            telemetryRow.addView(batteryCard, lpMatchWrap(bottom = 16))
        } else {
            telemetryRow.addView(speedCard, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = 16 })
            telemetryRow.addView(batteryCard, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        }
        root.addView(telemetryRow, lpMatchWrap(bottom = 18))

        // Cabin Climate (HVAC) Card
        val hvacCard = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = cardBg("#334155", "#0F172A")
            setPadding(28, 18, 28, 18)
        }
        val hvacLabel = TextView(this).apply {
            id = R.id.txt_hvac_label
            text = getString(R.string.hvac_label)
            setTextColor(Color.parseColor("#CBD5E1"))
            textSize = 18f
            typeface = Typeface.DEFAULT_BOLD
        }
        txtHvacTemp = TextView(this).apply {
            id = R.id.txt_hvac_temp
            text = "21.5 °C"
            setTextColor(Color.parseColor("#FB923C"))
            textSize = 26f
            typeface = Typeface.DEFAULT_BOLD
        }
        hvacCard.addView(hvacLabel, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        hvacCard.addView(txtHvacTemp, lpWrap())
        root.addView(hvacCard, lpMatchWrap(bottom = 18))

        // Charging Schedule Card (v1.0 vs v1.1 declared change CHG-101)
        val scheduleCard = LinearLayout(this).apply {
            id = if (BuildVariantConfig.IS_V1_1) R.id.card_charging_schedule_v2 else R.id.card_charging_schedule_v1
            orientation = LinearLayout.VERTICAL
            background = cardBg(if (BuildVariantConfig.IS_V1_1) "#2E74C9" else "#334155", "#0F172A")
            setPadding(28, 20, 28, 20)
        }
        val schedTitle = TextView(this).apply {
            id = R.id.txt_charging_title
            text = if (BuildVariantConfig.IS_V1_1) getString(R.string.charging_title_v2) else getString(R.string.charging_title)
            setTextColor(Color.WHITE)
            textSize = 18f
            typeface = Typeface.DEFAULT_BOLD
        }
        inputChargeNote = EditText(this).apply {
            id = R.id.input_charge_note
            hint = "Charging note (locked while driving)"
            setTextColor(Color.WHITE)
            setHintTextColor(Color.parseColor("#64748B"))
            setBackgroundColor(Color.parseColor("#1E293B"))
            setPadding(16, 12, 16, 12)
        }
        val actionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(0, 14, 0, 0)
        }
        btnOpenChargingModal = Button(this).apply {
            id = R.id.btn_open_charging_modal
            text = getString(R.string.btn_open_modal)
            setTextColor(Color.WHITE)
            setBackgroundColor(Color.parseColor("#2E74C9"))
            setPadding(24, 14, 24, 14)
            setOnClickListener { openChargingScheduleModal() }
        }
        val btnNavShortcut = Button(this).apply {
            id = if (BuildVariantConfig.IS_V1_1) R.id.btn_nav_shortcut_v2 else R.id.btn_nav_shortcut_v1
            text = if (BuildVariantConfig.IS_V1_1) getString(R.string.nav_shortcut_v2) else getString(R.string.nav_shortcut_v1)
            setTextColor(Color.parseColor("#E2E8F0"))
            setBackgroundColor(Color.parseColor("#1E293B"))
            setPadding(24, 14, 24, 14)
            setOnClickListener { Log.i(TAG, "Navigation shortcut tapped (${BuildVariantConfig.RELEASE_TAG})") }
        }
        actionRow.addView(btnOpenChargingModal, lpWrap(right = 14))
        actionRow.addView(btnNavShortcut, lpWrap())

        scheduleCard.addView(schedTitle, lpMatchWrap(bottom = 10))
        scheduleCard.addView(inputChargeNote, lpMatchWrap())
        scheduleCard.addView(actionRow, lpMatchWrap())
        root.addView(scheduleCard, lpMatchWrap())

        scroll.addView(root)
        setContentView(scroll)
    }

    private fun lpMatchWrap(top: Int = 0, bottom: Int = 0): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = top
            bottomMargin = bottom
        }
    }

    private fun lpWrap(right: Int = 0): LinearLayout.LayoutParams {
        return LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            rightMargin = right
        }
    }
}
