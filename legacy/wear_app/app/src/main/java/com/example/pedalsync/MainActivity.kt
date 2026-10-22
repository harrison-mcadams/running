package com.example.pedalsync

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat

class MainActivity : ComponentActivity() {

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        // Permissions granted
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        checkAndRequestPermissions()

        setContent {
            PedalSyncWearTheme {
                PedalSyncWearScreen(
                    onStartClick = { ip -> startStreaming(ip) },
                    onStopClick = { stopStreaming() }
                )
            }
        }
    }

    private fun checkAndRequestPermissions() {
        val permissions = mutableListOf(
            Manifest.permission.BODY_SENSORS,
            Manifest.permission.INTERNET
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.POST_NOTIFICATIONS)
        }

        val missing = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missing.isNotEmpty()) {
            requestPermissionLauncher.launch(missing.toTypedArray())
        }
    }

    private fun startStreaming(serverIp: String) {
        val intent = Intent(this, SensorStreamService::class.java).apply {
            putExtra(SensorStreamService.EXTRA_SERVER_IP, serverIp)
        }
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(intent)
            } else {
                startService(intent)
            }
        } catch (e: Exception) {
            try { startService(intent) } catch (err: Exception) { err.printStackTrace() }
        }
    }

    private fun stopStreaming() {
        val intent = Intent(this, SensorStreamService::class.java)
        stopService(intent)
    }
}

@Composable
fun PedalSyncWearTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = Color(0xFF00F2FE),
            secondary = Color(0xFF00FF88),
            background = Color(0xFF0A0E17),
            surface = Color(0xFF121A2A)
        ),
        content = content
    )
}

@Composable
fun PedalSyncWearScreen(
    onStartClick: (String) -> Unit,
    onStopClick: () -> Unit
) {
    val isStreaming by SensorStreamService.isStreaming.collectAsState()
    val samplesSent by SensorStreamService.samplesSent.collectAsState()
    var ipInput by remember { mutableStateOf("192.168.1.169:8088") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0A0E17))
            .padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "⌚ PedalSync Wear",
            fontSize = 16.sp,
            fontWeight = FontWeight.Bold,
            color = Color(0xFF00F2FE),
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(8.dp))

        OutlinedTextField(
            value = ipInput,
            onValueChange = { ipInput = it },
            label = { Text("Server IP", fontSize = 10.sp, color = Color.Gray) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(0.9f)
        )

        Spacer(modifier = Modifier.height(12.dp))

        Button(
            onClick = {
                if (isStreaming) {
                    onStopClick()
                } else {
                    onStartClick(ipInput)
                }
            },
            modifier = Modifier
                .size(width = 140.dp, height = 48.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = if (isStreaming) Color(0xFFFF007F) else Color(0xFF00FF88)
            ),
            shape = CircleShape
        ) {
            Text(
                text = if (isStreaming) "⏹ STOP" else "🚀 STREAM",
                color = Color.Black,
                fontWeight = FontWeight.Bold,
                fontSize = 14.sp
            )
        }

        Spacer(modifier = Modifier.height(10.dp))

        Text(
            text = if (isStreaming) "LIVE ⚡ Sent: $samplesSent" else "READY",
            fontSize = 12.sp,
            color = if (isStreaming) Color(0xFF00FF88) else Color.Gray,
            fontWeight = FontWeight.SemiBold
        )
    }
}
