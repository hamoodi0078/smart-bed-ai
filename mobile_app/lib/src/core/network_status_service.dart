import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// Whether the device currently has internet connectivity.
final networkStatusProvider = StreamProvider<NetworkStatus>((ref) {
  final service = NetworkStatusService();
  ref.onDispose(service.dispose);
  return service.statusStream;
});

/// Simplified convenience provider — true when online.
final isOnlineProvider = Provider<bool>((ref) {
  final status = ref.watch(networkStatusProvider);
  return status.maybeWhen(
    data: (s) => s == NetworkStatus.online,
    orElse: () => true, // assume online until proven otherwise
  );
});

enum NetworkStatus { online, offline }

class NetworkStatusService {
  NetworkStatusService() {
    _subscription = Connectivity()
        .onConnectivityChanged
        .listen(_onConnectivityChanged);
    // Fire an initial check.
    Connectivity().checkConnectivity().then(_onConnectivityChanged);
  }

  final _controller = StreamController<NetworkStatus>.broadcast();
  StreamSubscription<List<ConnectivityResult>>? _subscription;

  Stream<NetworkStatus> get statusStream => _controller.stream;

  void _onConnectivityChanged(List<ConnectivityResult> results) {
    final hasConnection = results.any(
      (r) => r != ConnectivityResult.none,
    );
    _controller.add(
      hasConnection ? NetworkStatus.online : NetworkStatus.offline,
    );
  }

  void dispose() {
    _subscription?.cancel();
    _controller.close();
  }
}
