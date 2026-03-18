import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final deviceConnectivityServiceProvider = Provider<DeviceConnectivityService>(
  (ref) => const DeviceConnectivityService(),
);

class BluetoothStateSnapshot {
  const BluetoothStateSnapshot({
    required this.supported,
    required this.enabled,
    required this.permissionRequired,
  });

  final bool supported;
  final bool enabled;
  final bool permissionRequired;
}

class PairedBluetoothDevice {
  const PairedBluetoothDevice({
    required this.name,
    required this.address,
    required this.bondState,
  });

  final String name;
  final String address;
  final int bondState;
}

class PairedBluetoothDevicesSnapshot {
  const PairedBluetoothDevicesSnapshot({
    required this.supported,
    required this.permissionRequired,
    required this.devices,
  });

  final bool supported;
  final bool permissionRequired;
  final List<PairedBluetoothDevice> devices;
}

class DeviceConnectivityService {
  const DeviceConnectivityService();

  static const MethodChannel _channel = MethodChannel(
    'smart_bed/device_connectivity',
  );

  bool get _isAndroid =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  Future<bool> openWifiSettingsPanel() async {
    if (!_isAndroid) {
      return false;
    }
    try {
      final launched = await _channel.invokeMethod<bool>(
        'openWifiSettingsPanel',
      );
      return launched ?? false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  Future<bool> openBluetoothSettings() async {
    if (!_isAndroid) {
      return false;
    }
    try {
      final launched = await _channel.invokeMethod<bool>(
        'openBluetoothSettings',
      );
      return launched ?? false;
    } on PlatformException {
      return false;
    } on MissingPluginException {
      return false;
    }
  }

  Future<BluetoothStateSnapshot> bluetoothState() async {
    if (!_isAndroid) {
      return const BluetoothStateSnapshot(
        supported: false,
        enabled: false,
        permissionRequired: false,
      );
    }
    try {
      final payload = await _channel.invokeMethod<Map<dynamic, dynamic>>(
        'getBluetoothState',
      );
      return BluetoothStateSnapshot(
        supported: _boolFrom(payload, 'supported'),
        enabled: _boolFrom(payload, 'enabled'),
        permissionRequired: _boolFrom(payload, 'permissionRequired'),
      );
    } on PlatformException {
      return const BluetoothStateSnapshot(
        supported: false,
        enabled: false,
        permissionRequired: false,
      );
    } on MissingPluginException {
      return const BluetoothStateSnapshot(
        supported: false,
        enabled: false,
        permissionRequired: false,
      );
    }
  }

  Future<PairedBluetoothDevicesSnapshot> pairedBluetoothDevices() async {
    if (!_isAndroid) {
      return const PairedBluetoothDevicesSnapshot(
        supported: false,
        permissionRequired: false,
        devices: <PairedBluetoothDevice>[],
      );
    }
    try {
      final payload = await _channel.invokeMethod<Map<dynamic, dynamic>>(
        'listPairedBluetoothDevices',
      );
      final rawDevices = payload?['devices'];
      final parsedDevices = <PairedBluetoothDevice>[];
      if (rawDevices is List) {
        for (final row in rawDevices) {
          if (row is! Map) {
            continue;
          }
          parsedDevices.add(
            PairedBluetoothDevice(
              name: _stringFrom(row, 'name'),
              address: _stringFrom(row, 'address'),
              bondState: _intFrom(row, 'bondState'),
            ),
          );
        }
      }
      return PairedBluetoothDevicesSnapshot(
        supported: _boolFrom(payload, 'supported'),
        permissionRequired: _boolFrom(payload, 'permissionRequired'),
        devices: parsedDevices,
      );
    } on PlatformException {
      return const PairedBluetoothDevicesSnapshot(
        supported: false,
        permissionRequired: false,
        devices: <PairedBluetoothDevice>[],
      );
    } on MissingPluginException {
      return const PairedBluetoothDevicesSnapshot(
        supported: false,
        permissionRequired: false,
        devices: <PairedBluetoothDevice>[],
      );
    }
  }

  bool _boolFrom(Map<dynamic, dynamic>? payload, String key) {
    if (payload == null) {
      return false;
    }
    final value = payload[key];
    if (value is bool) {
      return value;
    }
    if (value is String) {
      final normalized = value.trim().toLowerCase();
      return normalized == 'true' || normalized == '1';
    }
    if (value is num) {
      return value != 0;
    }
    return false;
  }

  String _stringFrom(Map<dynamic, dynamic>? payload, String key) {
    if (payload == null) {
      return '';
    }
    return (payload[key] ?? '').toString().trim();
  }

  int _intFrom(Map<dynamic, dynamic>? payload, String key) {
    if (payload == null) {
      return 0;
    }
    final value = payload[key];
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.toInt();
    }
    return int.tryParse((value ?? '').toString()) ?? 0;
  }
}
