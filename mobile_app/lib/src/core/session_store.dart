import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'models.dart';

class SessionStore {
  const SessionStore();

  static const _sessionKey = 'smart_bed.mobile_auth_session';

  FlutterSecureStorage get _storage => const FlutterSecureStorage();

  Future<AuthSession?> read() async {
    final raw = await _storage.read(key: _sessionKey);
    if (raw == null || raw.isEmpty) {
      return null;
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) {
        return null;
      }
      return AuthSession.fromJson(decoded.cast<String, dynamic>());
    } catch (_) {
      await clear();
      return null;
    }
  }

  Future<void> write(AuthSession session) async {
    await _storage.write(key: _sessionKey, value: jsonEncode(session.toJson()));
  }

  Future<void> clear() {
    return _storage.delete(key: _sessionKey);
  }
}
