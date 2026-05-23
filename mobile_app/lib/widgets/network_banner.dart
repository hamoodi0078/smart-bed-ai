import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../src/core/network_status_service.dart';
import '../theme/app_theme.dart';

/// Thin orange banner that appears at the top of a screen when the device is
/// offline. Disappears automatically when connectivity is restored.
///
/// Usage — place as the first child inside your Column:
///   Column(
///     children: [
///       const NetworkBanner(),
///       ...
///     ],
///   )
class NetworkBanner extends ConsumerWidget {
  const NetworkBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isOnline = ref.watch(isOnlineProvider);
    return AnimatedCrossFade(
      duration: const Duration(milliseconds: 300),
      crossFadeState:
          isOnline ? CrossFadeState.showSecond : CrossFadeState.showFirst,
      firstChild: Material(
        color: Colors.transparent,
        child: Container(
          width: double.infinity,
          padding:
              const EdgeInsets.symmetric(horizontal: 16, vertical: 7),
          color: AppColors.orange.withValues(alpha: 0.92),
          child: const Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(Icons.wifi_off_rounded, color: Colors.white, size: 15),
              SizedBox(width: 8),
              Flexible(
                child: Text(
                  'No internet connection — showing cached data',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ],
          ),
        ),
      ),
      secondChild: const SizedBox.shrink(),
    );
  }
}

/// Guard that wraps an API call with a connectivity check.
/// Throws [OfflineException] if the device is offline.
///
/// Usage inside a ConsumerState:
///   await NetworkGuard.check(ref, () => ApiService.getDashboard());
class OfflineException implements Exception {
  const OfflineException();
  @override
  String toString() => 'No internet connection. Please check your network.';
}

class NetworkGuard {
  const NetworkGuard._();

  static Future<T> check<T>(
    WidgetRef ref,
    Future<T> Function() call,
  ) async {
    final isOnline = ref.read(isOnlineProvider);
    if (!isOnline) throw const OfflineException();
    return call();
  }
}
