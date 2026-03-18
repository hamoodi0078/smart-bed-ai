import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';

final deviceLocationServiceProvider = Provider<DeviceLocationService>(
  (ref) => const DeviceLocationService(),
);

class DeviceLocationSnapshot {
  const DeviceLocationSnapshot({
    required this.latitude,
    required this.longitude,
    required this.timezone,
  });

  final double latitude;
  final double longitude;
  final String timezone;
}

class DeviceLocationResult {
  const DeviceLocationResult({
    this.snapshot,
    this.permissionDenied = false,
    this.serviceDisabled = false,
  });

  final DeviceLocationSnapshot? snapshot;
  final bool permissionDenied;
  final bool serviceDisabled;
}

class DeviceLocationService {
  const DeviceLocationService();

  Future<DeviceLocationResult> captureCurrentLocation() async {
    final serviceEnabled = await Geolocator.isLocationServiceEnabled();
    if (!serviceEnabled) {
      return const DeviceLocationResult(serviceDisabled: true);
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }

    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      return const DeviceLocationResult(permissionDenied: true);
    }

    final position = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.medium,
        distanceFilter: 100,
      ),
    );

    return DeviceLocationResult(
      snapshot: DeviceLocationSnapshot(
        latitude: position.latitude,
        longitude: position.longitude,
        timezone: _currentTimezone(),
      ),
    );
  }

  String _currentTimezone() {
    final raw = DateTime.now().timeZoneName.trim();
    return raw.isEmpty ? 'UTC' : raw;
  }
}

