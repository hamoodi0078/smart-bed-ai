package com.example.mobile_app

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.Settings
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    companion object {
        private const val CHANNEL = "smart_bed/device_connectivity"
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            CHANNEL,
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "openWifiSettingsPanel" -> result.success(openWifiSettingsPanel())
                "openBluetoothSettings" -> result.success(openBluetoothSettings())
                "getBluetoothState" -> result.success(bluetoothStatePayload())
                "listPairedBluetoothDevices" -> result.success(pairedBluetoothPayload())
                else -> result.notImplemented()
            }
        }
    }

    private fun openWifiSettingsPanel(): Boolean {
        val intent = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            Intent(Settings.Panel.ACTION_INTERNET_CONNECTIVITY)
        } else {
            Intent(Settings.ACTION_WIFI_SETTINGS)
        }
        return launchIntent(intent)
    }

    private fun openBluetoothSettings(): Boolean {
        return launchIntent(Intent(Settings.ACTION_BLUETOOTH_SETTINGS))
    }

    private fun launchIntent(intent: Intent): Boolean {
        return try {
            startActivity(intent)
            true
        } catch (_: ActivityNotFoundException) {
            false
        } catch (_: SecurityException) {
            false
        }
    }

    private fun bluetoothAdapter(): BluetoothAdapter? {
        val manager = getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager
        return manager?.adapter
    }

    private fun hasBluetoothConnectPermission(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) {
            return true
        }
        val granted = ContextCompat.checkSelfPermission(
            this,
            Manifest.permission.BLUETOOTH_CONNECT,
        )
        return granted == PackageManager.PERMISSION_GRANTED
    }

    private fun bluetoothStatePayload(): Map<String, Any> {
        val adapter = bluetoothAdapter()
        val supported = adapter != null
        val permissionRequired = supported && !hasBluetoothConnectPermission()
        val enabled = supported && !permissionRequired && (adapter?.isEnabled == true)
        return mapOf(
            "supported" to supported,
            "enabled" to enabled,
            "permissionRequired" to permissionRequired,
        )
    }

    private fun pairedBluetoothPayload(): Map<String, Any> {
        val adapter = bluetoothAdapter()
        if (adapter == null) {
            return mapOf(
                "supported" to false,
                "permissionRequired" to false,
                "devices" to emptyList<Map<String, Any>>(),
            )
        }
        if (!hasBluetoothConnectPermission()) {
            return mapOf(
                "supported" to true,
                "permissionRequired" to true,
                "devices" to emptyList<Map<String, Any>>(),
            )
        }

        val rows = try {
            adapter.bondedDevices
                ?.map { device ->
                    mapOf(
                        "name" to (device.name ?: "Unnamed device"),
                        "address" to (device.address ?: ""),
                        "bondState" to device.bondState,
                    )
                }
                ?.sortedBy { row -> (row["name"] as? String) ?: "" }
                ?: emptyList()
        } catch (_: SecurityException) {
            emptyList()
        }

        return mapOf(
            "supported" to true,
            "permissionRequired" to false,
            "devices" to rows,
        )
    }
}
