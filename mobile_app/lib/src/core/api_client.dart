import 'package:dio/dio.dart';

import '../config/app_config.dart';
import 'models.dart';

class ApiException implements Exception {
  const ApiException({
    required this.message,
    this.statusCode,
    this.code,
    this.traceId,
  });

  final String message;
  final int? statusCode;
  final String? code;
  final String? traceId;

  factory ApiException.unauthenticated([
    String message = 'Please sign in again.',
  ]) {
    return ApiException(
      message: message,
      statusCode: 401,
      code: 'UNAUTHORIZED',
    );
  }

  @override
  String toString() => message;
}

class SmartBedApi {
  SmartBedApi({Dio? dio, String? baseUrl})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl: baseUrl ?? AppConfig.apiBaseUrl,
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 15),
              sendTimeout: const Duration(seconds: 10),
              validateStatus: (status) => status != null && status < 600,
              headers: const <String, Object>{'Accept': 'application/json'},
            ),
          );

  final Dio _dio;

  String get baseUrl => _dio.options.baseUrl;

  Future<AuthSession> register({
    required String email,
    required String password,
    required String name,
  }) async {
    final json = await _post(
      '/v1/mobile/auth/register',
      data: <String, Object>{
        'email': email,
        'password': password,
        'name': name,
      },
    );
    return AuthSession.fromJson(json);
  }

  Future<AuthSession> login({
    required String email,
    required String password,
  }) async {
    final json = await _post(
      '/v1/mobile/auth/login',
      data: <String, Object>{'email': email, 'password': password},
    );
    return AuthSession.fromJson(json);
  }

  Future<OtpRequestResult> requestOtp({
    required String phoneNumber,
    String clientName = 'flutter_app',
  }) async {
    final json = await _post(
      '/v1/mobile/auth/otp/request',
      data: <String, Object>{
        'phone_number': phoneNumber,
        'client_name': clientName,
      },
    );
    return OtpRequestResult.fromJson(json);
  }

  Future<AuthSession> verifyOtp({
    required String requestId,
    required String phoneNumber,
    required String otpCode,
    String name = '',
    String clientName = 'flutter_app',
  }) async {
    final json = await _post(
      '/v1/mobile/auth/otp/verify',
      data: <String, Object>{
        'request_id': requestId,
        'phone_number': phoneNumber,
        'otp_code': otpCode,
        'name': name,
        'client_name': clientName,
      },
    );
    return AuthSession.fromJson(json);
  }

  Future<AuthSession> socialLogin({
    required String provider,
    String providerUserId = '',
    String providerAccessToken = '',
    String providerIdToken = '',
    String providerAuthCode = '',
    String email = '',
    String name = '',
    String clientName = 'flutter_app',
  }) async {
    final json = await _post(
      '/v1/mobile/auth/social',
      data: <String, Object>{
        'provider': provider,
        'provider_user_id': providerUserId,
        'provider_access_token': providerAccessToken,
        'provider_id_token': providerIdToken,
        'provider_auth_code': providerAuthCode,
        'email': email,
        'name': name,
        'client_name': clientName,
      },
    );
    return AuthSession.fromJson(json);
  }

  Future<AuthSession> refresh(String refreshToken) async {
    final json = await _post(
      '/v1/mobile/auth/refresh',
      data: <String, Object>{'refresh_token': refreshToken},
    );
    return AuthSession.fromJson(json);
  }

  Future<void> logout({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _post(
      '/v1/mobile/auth/logout',
      data: <String, Object>{
        'access_token': accessToken,
        'refresh_token': refreshToken,
      },
      accessToken: accessToken,
    );
  }

  Future<MobileUser> me(String accessToken) async {
    final json = await _get('/v1/mobile/auth/me', accessToken: accessToken);
    return MobileUser.fromJson(_asMap(json['user'], 'user'));
  }

  Future<BedStateSnapshot> getBedState(String accessToken) async {
    final json = await _get('/v2/bed/state', accessToken: accessToken);
    return BedStateSnapshot.fromJson(json);
  }

  Future<DashboardSummary> getDashboard(String accessToken) async {
    final json = await _get('/v1/mobile/dashboard', accessToken: accessToken);
    return DashboardSummary.fromJson(json);
  }

  Future<SceneGallery> getScenes(String accessToken) async {
    final json = await _get('/v1/mobile/scenes', accessToken: accessToken);
    return SceneGallery.fromJson(json);
  }

  Future<ScenePreviewResult> previewScene({
    required String accessToken,
    required String sceneKey,
  }) async {
    final json = await _post(
      '/v1/mobile/scenes/preview',
      data: <String, Object>{'scene_key': sceneKey},
      accessToken: accessToken,
    );
    return ScenePreviewResult.fromJson(json);
  }

  Future<SceneSaveResult> saveSceneForTonight({
    required String accessToken,
    required String sceneKey,
  }) async {
    final json = await _post(
      '/v1/mobile/scenes/save-tonight',
      data: <String, Object>{'scene_key': sceneKey},
      accessToken: accessToken,
    );
    return SceneSaveResult.fromJson(json);
  }

  Future<List<TimelineItem>> getTimeline(String accessToken) async {
    final json = await _get('/v1/mobile/timeline', accessToken: accessToken);
    final items = json['items'] is List
        ? json['items'] as List
        : const <Object?>[];
    return items
        .map((item) => TimelineItem.fromJson(_asMap(item, 'timeline item')))
        .toList(growable: false);
  }

  Future<FirstThreeNightsChecklist> getFirstThreeNightsChecklist(
    String accessToken,
  ) async {
    final json = await _get(
      '/v1/mobile/first-3-nights',
      accessToken: accessToken,
    );
    return FirstThreeNightsChecklist.fromJson(
      _asMap(json['checklist'], 'first 3 nights checklist'),
    );
  }

  Future<FirstThreeNightsChecklist> completeFirstThreeNightsStep({
    required String accessToken,
    required String stepKey,
  }) async {
    final json = await _post(
      '/v1/mobile/first-3-nights/complete',
      data: <String, Object>{'step_key': stepKey},
      accessToken: accessToken,
    );
    return FirstThreeNightsChecklist.fromJson(
      _asMap(json['checklist'], 'first 3 nights checklist'),
    );
  }

  Future<NightlySummaryFeedback> submitNightlySummaryFeedback({
    required String accessToken,
    required String vote,
    String summaryGeneratedAtUtc = '',
  }) async {
    final payload = <String, Object>{'vote': vote};
    if (summaryGeneratedAtUtc.trim().isNotEmpty) {
      payload['summary_generated_at_utc'] = summaryGeneratedAtUtc.trim();
    }
    final json = await _post(
      '/v1/mobile/nightly-summary/feedback',
      data: payload,
      accessToken: accessToken,
    );
    return NightlySummaryFeedback.fromJson(
      _asMap(json['feedback'], 'nightly summary feedback'),
    );
  }

  Future<AutomationFeedbackLoop> submitCommandFeedback({
    required String accessToken,
    required String commandId,
    required String vote,
    String note = '',
  }) async {
    final payload = <String, Object>{'vote': vote};
    if (note.trim().isNotEmpty) {
      payload['note'] = note.trim();
    }
    final json = await _post(
      '/v1/mobile/device-commands/$commandId/feedback',
      data: payload,
      accessToken: accessToken,
    );
    return AutomationFeedbackLoop.fromJson(
      _asMap(json['feedback'], 'command feedback'),
    );
  }

  Future<BetaMetrics> getBetaMetrics(String accessToken) async {
    final json = await _get(
      '/v1/mobile/beta/metrics',
      accessToken: accessToken,
    );
    return BetaMetrics.fromJson(_asMap(json['metrics'], 'beta metrics'));
  }

  Future<UserSettings> getSettings(String accessToken) async {
    final json = await _get('/v1/mobile/settings', accessToken: accessToken);
    return UserSettings.fromJson(_asMap(json['settings'], 'settings'));
  }

  Future<UserSettings> updateSettings({
    required String accessToken,
    required UserSettings settings,
  }) async {
    final json = await _post(
      '/v1/mobile/settings',
      data: settings.toJson(),
      accessToken: accessToken,
    );
    return UserSettings.fromJson(_asMap(json['settings'], 'settings'));
  }

  Future<UserProfilePrefs> getProfile(String accessToken) async {
    final json = await _get('/v1/mobile/profile', accessToken: accessToken);
    return UserProfilePrefs.fromJson(_asMap(json['profile'], 'profile'));
  }

  Future<UserProfilePrefs> updateProfile({
    required String accessToken,
    required UserProfilePrefs profile,
  }) async {
    final json = await _post(
      '/v1/mobile/profile',
      data: profile.toJson(),
      accessToken: accessToken,
    );
    return UserProfilePrefs.fromJson(_asMap(json['profile'], 'profile'));
  }

  Future<IslamicOverview> getIslamicOverview(String accessToken) async {
    final json = await _get(
      '/v1/mobile/islamic/overview',
      accessToken: accessToken,
    );
    return IslamicOverview.fromJson(json);
  }

  Future<String> sendChatMessage({
    required String accessToken,
    required String message,
  }) async {
    final json = await _post(
      '/v1/ai/chat',
      data: <String, Object>{'message': message},
      accessToken: accessToken,
    );
    return _string(json['reply'], fallback: 'Dana is unavailable right now.');
  }

  Future<SubscriptionStatus> getSubscriptionStatus(String accessToken) async {
    final json = await _get(
      '/v1/mobile/subscription/status',
      accessToken: accessToken,
    );
    return SubscriptionStatus.fromJson(json);
  }

  Future<List<BillingHistoryEvent>> getSubscriptionHistory(
    String accessToken, {
    int limit = 12,
  }) async {
    final json = await _get(
      '/v1/mobile/subscription/history',
      accessToken: accessToken,
      queryParameters: <String, Object>{'limit': limit},
    );
    final items = json['events'] is List
        ? json['events'] as List
        : const <Object?>[];
    return items
        .map((item) => BillingHistoryEvent.fromJson(_asMap(item, 'billing event')))
        .toList(growable: false);
  }

  Future<CheckoutSessionInfo> createSubscriptionCheckout({
    required String accessToken,
    required String tier,
    required String interval,
    String returnUrl = '',
    String cancelUrl = '',
  }) async {
    final json = await _post(
      '/v1/mobile/subscription/checkout',
      data: <String, Object>{
        'tier': tier,
        'interval': interval,
        'return_url': returnUrl,
        'cancel_url': cancelUrl,
      },
      accessToken: accessToken,
    );
    return CheckoutSessionInfo.fromJson(
      _asMap(json['checkout'], 'checkout session'),
    );
  }

  Future<String> pauseActiveSubscription({
    required String accessToken,
    String reason = '',
  }) async {
    final json = await _post(
      '/v1/mobile/subscription/pause',
      data: <String, Object>{'reason': reason},
      accessToken: accessToken,
    );
    return _string(json['message'], fallback: 'Subscription paused.');
  }

  Future<String> cancelActiveSubscription({
    required String accessToken,
    String reason = '',
  }) async {
    final json = await _post(
      '/v1/mobile/subscription/cancel-active',
      data: <String, Object>{'reason': reason},
      accessToken: accessToken,
    );
    return _string(json['message'], fallback: 'Subscription cancelled.');
  }

  Future<DeviceCommandReceipt> createDeviceCommand({
    required String accessToken,
    required String action,
  }) async {
    final json = await _post(
      '/v1/mobile/device-commands',
      data: <String, Object>{'action': action},
      accessToken: accessToken,
    );
    return DeviceCommandReceipt.fromJson(json);
  }

  Future<UndoStatus> getUndoStatus(String accessToken) async {
    final json = await _get(
      '/v1/mobile/actions/undo/status',
      accessToken: accessToken,
    );
    return UndoStatus.fromJson(json);
  }

  Future<UndoResult> undoLastAction(String accessToken) async {
    final json = await _post(
      '/v1/mobile/actions/undo',
      data: const <String, Object>{},
      accessToken: accessToken,
    );
    return UndoResult.fromJson(json);
  }

  Future<TrialStatus> getTrialStatus({
    required String userId,
    String? accessToken,
  }) async {
    final json = await _get(
      '/v1/subscriptions/trial/status',
      queryParameters: <String, Object>{'user_id': userId},
      accessToken: accessToken,
    );
    return TrialStatus.fromJson(json);
  }

  Future<TrialStatus> startTrial({
    required String userId,
    required String accessToken,
  }) async {
    await _post(
      '/v1/subscriptions/trial/start',
      data: <String, Object>{'user_id': userId},
      accessToken: accessToken,
    );
    return getTrialStatus(userId: userId, accessToken: accessToken);
  }

  Future<DeviceControls> getDeviceControls(String accessToken) async {
    final json = await _get(
      '/v1/mobile/device-controls',
      accessToken: accessToken,
    );
    return DeviceControls.fromJson(
      _asMap(json['controls'], 'device controls'),
    );
  }

  Future<DeviceControls> updateDeviceControls({
    required String accessToken,
    required DeviceControls controls,
  }) async {
    final json = await _post(
      '/v1/mobile/device-controls',
      data: controls.toJson(),
      accessToken: accessToken,
    );
    return DeviceControls.fromJson(
      _asMap(json['controls'], 'device controls'),
    );
  }

  Future<BedPairingStatus> getBedPairingStatus(String accessToken) async {
    final json = await _get(
      '/v1/mobile/bed/pairing',
      accessToken: accessToken,
    );
    return BedPairingStatus.fromJson(json);
  }

  Future<BedPairingStatus> pairBed({
    required String accessToken,
    String qrPayload = '',
    String deviceId = '',
    String claimToken = '',
    String bedLocation = 'Kuwait',
  }) async {
    final json = await _post(
      '/v1/mobile/bed/pair',
      data: <String, Object>{
        'qr_payload': qrPayload,
        'device_id': deviceId,
        'claim_token': claimToken,
        'bed_location': bedLocation,
      },
      accessToken: accessToken,
    );
    return BedPairingStatus.fromJson(json);
  }

  Future<void> unpairBed({
    required String accessToken,
    String deviceId = '',
  }) async {
    await _post(
      '/v1/mobile/bed/unpair',
      data: <String, Object>{'device_id': deviceId},
      accessToken: accessToken,
    );
  }

  Future<List<AlarmSchedule>> getAlarms(String accessToken) async {
    final json = await _get('/v1/mobile/alarms', accessToken: accessToken);
    final raw = json['alarms'] is List ? json['alarms'] as List : const <Object?>[];
    return raw
        .map((item) => AlarmSchedule.fromJson(_asMap(item, 'alarm')))
        .toList(growable: false);
  }

  Future<List<AlarmSchedule>> upsertAlarm({
    required String accessToken,
    required AlarmSchedule alarm,
  }) async {
    final json = await _post(
      '/v1/mobile/alarms',
      data: alarm.toJson(),
      accessToken: accessToken,
    );
    final raw = json['alarms'] is List ? json['alarms'] as List : const <Object?>[];
    return raw
        .map((item) => AlarmSchedule.fromJson(_asMap(item, 'alarm')))
        .toList(growable: false);
  }

  Future<void> toggleAlarm({
    required String accessToken,
    required String alarmId,
    required bool enabled,
  }) async {
    await _post(
      '/v1/mobile/alarms/$alarmId/toggle',
      data: <String, Object>{'enabled': enabled},
      accessToken: accessToken,
    );
  }

  Future<void> deleteAlarm({
    required String accessToken,
    required String alarmId,
  }) async {
    await _delete('/v1/mobile/alarms/$alarmId', accessToken: accessToken);
  }

  Future<String> getSpotifyAuthUrl({
    required String accessToken,
    String doneUri = '',
  }) async {
    final json = await _get(
      '/v1/mobile/spotify/auth-url',
      accessToken: accessToken,
      queryParameters: <String, Object>{'done_uri': doneUri},
    );
    return _string(json['auth_url']);
  }

  Future<SpotifyConnectionStatus> getSpotifyStatus(String accessToken) async {
    final json = await _get('/v1/mobile/spotify/status', accessToken: accessToken);
    return SpotifyConnectionStatus.fromJson(json);
  }

  Future<SpotifyPlaybackStatus> getSpotifyPlaybackStatus(
    String accessToken,
  ) async {
    final json = await _get(
      '/v1/mobile/spotify/playback-status',
      accessToken: accessToken,
    );
    return SpotifyPlaybackStatus.fromJson(json);
  }

  Future<String> spotifyPlaybackAction({
    required String accessToken,
    required String action,
    String deviceId = '',
    String playlistUri = '',
    int volumePercent = 50,
  }) async {
    final json = await _post(
      '/v1/mobile/spotify/playback',
      data: <String, Object>{
        'action': action,
        'device_id': deviceId,
        'playlist_uri': playlistUri,
        'volume_percent': volumePercent,
      },
      accessToken: accessToken,
    );
    return _string(json['message'], fallback: 'Spotify action sent.');
  }

  Future<void> disconnectSpotify({required String accessToken}) async {
    await _post(
      '/v1/mobile/spotify/disconnect',
      data: const <String, Object>{},
      accessToken: accessToken,
    );
  }

  Future<MobileDeviceInfo> getMobileDeviceInfo(String accessToken) async {
    final json = await _get('/v1/mobile/devices', accessToken: accessToken);
    return MobileDeviceInfo.fromJson(json);
  }

  Future<Map<String, dynamic>> _get(
    String path, {
    Map<String, Object>? queryParameters,
    String? accessToken,
  }) async {
    try {
      final response = await _dio.get<Object?>(
        path,
        queryParameters: queryParameters,
        options: _options(accessToken),
      );
      return _decodeResponse(response);
    } on DioException catch (error) {
      throw _networkException(error);
    }
  }

  Future<Map<String, dynamic>> _post(
    String path, {
    Object? data,
    String? accessToken,
  }) async {
    try {
      final response = await _dio.post<Object?>(
        path,
        data: data,
        options: _options(accessToken),
      );
      return _decodeResponse(response);
    } on DioException catch (error) {
      throw _networkException(error);
    }
  }

  Future<Map<String, dynamic>> _delete(
    String path, {
    String? accessToken,
  }) async {
    try {
      final response = await _dio.delete<Object?>(
        path,
        options: _options(accessToken),
      );
      return _decodeResponse(response);
    } on DioException catch (error) {
      throw _networkException(error);
    }
  }

  Options _options(String? accessToken) {
    final headers = <String, Object>{};
    if (accessToken != null && accessToken.isNotEmpty) {
      headers['Authorization'] = 'Bearer $accessToken';
    }
    return Options(headers: headers);
  }

  Map<String, dynamic> _decodeResponse(Response<Object?> response) {
    final json = _asMap(response.data, 'response');
    final statusCode = response.statusCode ?? 500;
    if (statusCode >= 200 && statusCode < 300) {
      return json;
    }

    final error = _asMap(json['error'], 'error');
    final fallbackDetail = _string(json['detail'], fallback: 'Request failed.');
    throw ApiException(
      message: _string(error['message'], fallback: fallbackDetail),
      statusCode: statusCode,
      code: _string(error['code']),
      traceId: _string(error['trace_id']),
    );
  }

  Map<String, dynamic> _asMap(Object? value, String label) {
    if (value is Map<String, dynamic>) {
      return value;
    }
    if (value is Map) {
      return value.map((key, item) => MapEntry(key.toString(), item));
    }
    throw ApiException(message: 'Unexpected $label payload from API.');
  }

  String _string(Object? value, {String fallback = ''}) {
    final text = value?.toString().trim() ?? '';
    return text.isEmpty ? fallback : text;
  }

  ApiException _networkException(DioException error) {
    if (error.type == DioExceptionType.connectionTimeout ||
        error.type == DioExceptionType.receiveTimeout ||
        error.type == DioExceptionType.sendTimeout) {
      return const ApiException(
        message:
            'The Danah backend timed out. Check the local server and try again.',
      );
    }
    if (error.type == DioExceptionType.connectionError ||
        (error.type == DioExceptionType.unknown &&
            (error.message ?? '').contains('XMLHttpRequest onError callback'))) {
      return ApiException(
        message:
            'Unable to reach the Danah backend at ${_dio.options.baseUrl}. Start the backend server and try again.',
      );
    }
    return ApiException(
      message: error.message ?? 'Unable to reach the Danah backend.',
    );
  }
}
