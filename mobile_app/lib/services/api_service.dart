import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

class ApiService {
  static const String baseUrl = 'http://localhost:8000';
  static const String _tokenKey = 'auth_token';
  static const String _chatFallback =
      'Dana is unavailable right now. Please try again. 🌙';

  static Future<void> saveToken(String token) async {
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.setString(_tokenKey, token);
    } catch (_) {}
  }

  static Future<String?> getToken() async {
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      return prefs.getString(_tokenKey);
    } catch (_) {
      return null;
    }
  }

  static Future<void> clearToken() async {
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.remove(_tokenKey);
    } catch (_) {}
  }

  static Future<Map<String, String>> _authHeaders() async {
    try {
      final String? token = await getToken();
      return <String, String>{
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ${token ?? ''}',
      };
    } catch (_) {
      return <String, String>{
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ',
      };
    }
  }

  static Future<Map<String, dynamic>> register(
    String email,
    String password,
    String name,
  ) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/auth/register'),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(<String, dynamic>{
          'email': email,
          'password': password,
          'name': name,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> login(
    String email,
    String password,
  ) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/auth/login'),
        headers: const <String, String>{'Content-Type': 'application/json'},
        body: jsonEncode(<String, dynamic>{
          'email': email,
          'password': password,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);

      final dynamic token = decoded['token'] ?? decoded['access_token'];
      if (token is String && token.isNotEmpty) {
        await saveToken(token);
      }

      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<void> logout() async {
    try {
      await clearToken();
    } catch (_) {}
  }

  static Future<Map<String, dynamic>> getBedStatus() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/bed/status'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> setLighting(
    String color,
    int brightness,
  ) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/bed/lighting'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'color': color,
          'brightness': brightness,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> setAlarm(
    String time,
    bool enabled,
  ) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/bed/alarms'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{
          'time': time,
          'enabled': enabled,
        }),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<String> sendMessage(String message) async {
    try {
      final http.Response response = await http.post(
        Uri.parse('$baseUrl/v1/ai/chat'),
        headers: await _authHeaders(),
        body: jsonEncode(<String, dynamic>{'message': message}),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      final dynamic reply = decoded['reply'];
      if (reply is String && reply.isNotEmpty) {
        return reply;
      }
      return _chatFallback;
    } catch (_) {
      return _chatFallback;
    }
  }

  static Future<Map<String, dynamic>> getPlan() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/plan'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Future<Map<String, dynamic>> getUsage() async {
    try {
      final http.Response response = await http.get(
        Uri.parse('$baseUrl/v1/mobile/usage'),
        headers: await _authHeaders(),
      );

      final Map<String, dynamic> decoded = _decodeResponse(response);
      _throwIfError(response, decoded);
      return decoded;
    } catch (e) {
      return _errorMap(e);
    }
  }

  static Map<String, dynamic> _decodeResponse(http.Response response) {
    if (response.body.isEmpty) {
      return <String, dynamic>{};
    }

    final dynamic decoded = jsonDecode(response.body);
    if (decoded is Map<String, dynamic>) {
      return decoded;
    }
    return <String, dynamic>{'data': decoded};
  }

  static void _throwIfError(
    http.Response response,
    Map<String, dynamic> decoded,
  ) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return;
    }

    final dynamic message = decoded['message'] ?? decoded['detail'];
    if (message is String && message.isNotEmpty) {
      throw Exception(message);
    }
    throw Exception('Request failed with status ${response.statusCode}');
  }

  static Map<String, dynamic> _errorMap(Object error) {
    return <String, dynamic>{
      'error': true,
      'message': error.toString(),
    };
  }
}
