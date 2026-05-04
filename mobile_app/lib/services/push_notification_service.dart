import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

import 'api_service.dart';

/// Lightweight push notification token manager.
///
/// The actual FCM/APNs token is written to SharedPreferences by whichever
/// native plugin is integrated (e.g. firebase_messaging).  This service reads
/// that token and registers it with the backend so the server can deliver
/// Expo-compatible push notifications.
///
/// To integrate FCM later, simply call [storeToken] from the FCM callback:
///   FirebaseMessaging.instance.onTokenRefresh.listen(PushNotificationService.storeToken);
class PushNotificationService {
  static const String _tokenKey = 'expo_push_token';

  /// Called by the native FCM plugin when a new token is issued.
  /// Stores the token locally and immediately syncs it to the backend.
  static Future<void> storeToken(String token) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_tokenKey, token);
      final platform = Platform.isIOS ? 'ios' : 'android';
      await ApiService.registerPushToken(token, platform: platform);
    } catch (_) {}
  }

  /// Called on app start / after login to re-register any stored token.
  /// This handles the case where the token was stored before the user logged in.
  static Future<void> syncStoredToken() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString(_tokenKey);
      if (token != null && token.isNotEmpty) {
        final platform = Platform.isIOS ? 'ios' : 'android';
        await ApiService.registerPushToken(token, platform: platform);
      }
    } catch (_) {}
  }
}
