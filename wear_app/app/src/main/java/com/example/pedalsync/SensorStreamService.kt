package com.example.pedalsync

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ConcurrentLinkedQueue

class SensorStreamService : Service(), SensorEventListener {

    private lateinit var sensorManager: SensorManager
    private var accelerometer: Sensor? = null
    private var wakeLock: PowerManager.WakeLock? = null

    private val sampleQueue = ConcurrentLinkedQueue<JSONObject>()
    private var streamJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO)

    override fun onCreate() {
        super.onCreate()
        sensorManager = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)

        val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "PedalSync::SensorStreamWakeLock")
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val serverIp = intent?.getStringExtra(EXTRA_SERVER_IP) ?: DEFAULT_SERVER_IP
        _serverAddress.value = serverIp

        try {
            startForegroundNotification()
        } catch (e: Exception) {
            Log.e("PedalSync", "startForeground failed, continuing as background service: ${e.message}")
        }

        try {
            wakeLock?.acquire(30 * 60 * 1000L /* 30 mins */)
        } catch (e: Exception) {
            Log.e("PedalSync", "WakeLock acquire failed: ${e.message}")
        }

        accelerometer?.let {
            sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME)
        }

        _isStreaming.value = true
        _samplesSent.value = 0

        // Start background HTTP transmission loop (100ms batches)
        streamJob?.cancel()
        streamJob = scope.launch {
            while (_isStreaming.value) {
                delay(100)
                flushBatch(serverIp)
            }
        }

        return START_STICKY
    }

    private fun flushBatch(serverIp: String) {
        if (sampleQueue.isEmpty()) return

        val batch = JSONArray()
        while (!sampleQueue.isEmpty() && batch.length() < 50) {
            sampleQueue.poll()?.let { batch.put(it) }
        }

        if (batch.length() == 0) return

        try {
            val urlStr = if (serverIp.startsWith("http://")) "$serverIp/api/imu_stream" else "http://$serverIp/api/imu_stream"
            val url = URL(urlStr)
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
            conn.doOutput = true
            conn.connectTimeout = 2000
            conn.readTimeout = 2000

            OutputStreamWriter(conn.outputStream).use { writer ->
                writer.write(batch.toString())
                writer.flush()
            }

            val responseCode = conn.responseCode
            if (responseCode == 200) {
                _samplesSent.value += batch.length()
            }
            conn.disconnect()
        } catch (e: Exception) {
            Log.w("PedalSync", "HTTP POST error: ${e.message}")
        }
    }

    override fun onSensorChanged(event: SensorEvent?) {
        if (event == null || event.sensor.type != Sensor.TYPE_ACCELEROMETER) return

        val sample = JSONObject().apply {
            put("timestamp", System.currentTimeMillis() / 1000.0)
            put("ax", event.values[0])
            put("ay", event.values[1])
            put("az", event.values[2])
        }

        sampleQueue.add(sample)
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {}

    override fun onDestroy() {
        super.onDestroy()
        _isStreaming.value = false
        sensorManager.unregisterListener(this)
        streamJob?.cancel()
        if (wakeLock?.isHeld == true) {
            try { wakeLock?.release() } catch (e: Exception) {}
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startForegroundNotification() {
        val channelId = "pedalsync_channel"
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                channelId,
                "PedalSync Sensor Stream",
                NotificationManager.IMPORTANCE_LOW
            )
            notificationManager.createNotificationChannel(channel)
        }

        val notification: Notification = NotificationCompat.Builder(this, channelId)
            .setContentTitle("PedalSync Wear OS")
            .setContentText("Streaming wrist motion at 50Hz...")
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setOngoing(true)
            .build()

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH)
            } catch (e: Exception) {
                startForeground(NOTIFICATION_ID, notification)
            }
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    companion object {
        const val NOTIFICATION_ID = 1001
        const val EXTRA_SERVER_IP = "EXTRA_SERVER_IP"
        const val DEFAULT_SERVER_IP = "192.168.1.169:8088"

        private val _isStreaming = MutableStateFlow(false)
        val isStreaming: StateFlow<Boolean> = _isStreaming

        private val _samplesSent = MutableStateFlow(0)
        val samplesSent: StateFlow<Int> = _samplesSent

        private val _serverAddress = MutableStateFlow(DEFAULT_SERVER_IP)
        val serverAddress: StateFlow<String> = _serverAddress
    }
}
