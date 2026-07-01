import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'session_store.dart';

class PushNotificationService {
  PushNotificationService._();

  static const String _tokenKey = 'expo_push_token';
  static const String _baseUrl = String.fromEnvironment(
    'SMART_BED_API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  static Future<void> storeToken(String token) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_tokenKey, token);
      final platform = Platform.isIOS ? 'ios' : 'android';
      await _registerPushToken(token, platform: platform);
    } catch (_) {}
  }

  static Future<void> syncStoredToken() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final token = prefs.getString(_tokenKey);
      if (token != null && token.isNotEmpty) {
        final platform = Platform.isIOS ? 'ios' : 'android';
        await _registerPushToken(token, platform: platform);
      }
    } catch (_) {}
  }

  static Future<void> _registerPushToken(String token, {required String platform}) async {
    try {
      final sessionStore = const SessionStore();
      final session = await sessionStore.read();
      final headers = <String, String>{
        'Content-Type': 'application/json',
      };
      if (session != null) {
        headers['Authorization'] = 'Bearer ${session.accessToken}';
      }
      await http.post(
        Uri.parse('$_baseUrl/v1/mobile/push-token'),
        headers: headers,
        body: jsonEncode(<String, dynamic>{
          'expo_token': token,
          'platform': platform,
        }),
      ).timeout(const Duration(seconds: 8));
    } catch (_) {}
  }
}
