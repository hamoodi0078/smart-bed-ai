import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../services/push_notification_service.dart';
import '../core/api_client.dart';
import '../core/device_location_service.dart';
import '../core/models.dart';
import '../core/session_store.dart';
import 'theme_controller.dart';

final sessionStoreProvider = Provider<SessionStore>(
  (ref) => const SessionStore(),
);

final smartBedApiProvider = Provider<SmartBedApi>((ref) => SmartBedApi());

final authControllerProvider = NotifierProvider<AuthController, AuthViewState>(
  AuthController.new,
);

class AuthViewState {
  const AuthViewState({
    required this.initialized,
    required this.isSubmitting,
    required this.session,
    required this.errorMessage,
  });

  const AuthViewState.loading()
    : initialized = false,
      isSubmitting = false,
      session = null,
      errorMessage = null;

  const AuthViewState.ready({
    required this.session,
    this.errorMessage,
    this.isSubmitting = false,
  }) : initialized = true;

  final bool initialized;
  final bool isSubmitting;
  final AuthSession? session;
  final String? errorMessage;

  AuthViewState copyWith({
    bool? initialized,
    bool? isSubmitting,
    AuthSession? session,
    bool clearSession = false,
    String? errorMessage,
    bool clearError = false,
  }) {
    return AuthViewState(
      initialized: initialized ?? this.initialized,
      isSubmitting: isSubmitting ?? this.isSubmitting,
      session: clearSession ? null : (session ?? this.session),
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
    );
  }
}

class AuthController extends Notifier<AuthViewState> {
  bool _bootstrapped = false;

  SessionStore get _store => ref.read(sessionStoreProvider);
  SmartBedApi get _api => ref.read(smartBedApiProvider);
  DeviceLocationService get _locationService =>
      ref.read(deviceLocationServiceProvider);
  ThemeController get _themeController =>
      ref.read(themeControllerProvider.notifier);

  @override
  AuthViewState build() {
    if (!_bootstrapped) {
      _bootstrapped = true;
      Future.microtask(_bootstrap);
    }
    return const AuthViewState.loading();
  }

  Future<void> signIn({required String email, required String password}) async {
    await _submit(() => _api.login(email: email, password: password));
  }

  Future<void> register({
    required String email,
    required String password,
    required String name,
  }) async {
    await _submit(
      () => _api.register(email: email, password: password, name: name),
    );
  }

  Future<OtpRequestResult> requestOtp({
    required String phoneNumber,
    String clientName = 'flutter_app',
  }) async {
    state = state.copyWith(isSubmitting: true, clearError: true);
    try {
      final result = await _api.requestOtp(
        phoneNumber: phoneNumber,
        clientName: clientName,
      );
      state = state.copyWith(isSubmitting: false, clearError: true);
      return result;
    } on ApiException catch (error) {
      state = state.copyWith(
        initialized: true,
        isSubmitting: false,
        errorMessage: error.message,
      );
      rethrow;
    }
  }

  Future<void> verifyOtp({
    required String requestId,
    required String phoneNumber,
    required String otpCode,
    String name = '',
    String clientName = 'flutter_app',
  }) async {
    await _submit(
      () => _api.verifyOtp(
        requestId: requestId,
        phoneNumber: phoneNumber,
        otpCode: otpCode,
        name: name,
        clientName: clientName,
      ),
    );
  }

  Future<void> signInWithSocial({
    required String provider,
    String providerUserId = '',
    String providerAccessToken = '',
    String providerIdToken = '',
    String providerAuthCode = '',
    String email = '',
    String name = '',
    String clientName = 'flutter_app',
  }) async {
    await _submit(
      () => _api.socialLogin(
        provider: provider,
        providerUserId: providerUserId,
        providerAccessToken: providerAccessToken,
        providerIdToken: providerIdToken,
        providerAuthCode: providerAuthCode,
        email: email,
        name: name,
        clientName: clientName,
      ),
    );
  }

  Future<void> signOut() async {
    final session = state.session;
    state = state.copyWith(isSubmitting: true, clearError: true);
    if (session != null) {
      try {
        await _api.logout(
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
        );
      } catch (_) {}
    }
    await _store.clear();
    state = const AuthViewState.ready(session: null);
  }

  Future<T> performAuthorized<T>(
    Future<T> Function(String accessToken) action,
  ) async {
    final session = state.session;
    if (session == null) {
      throw ApiException.unauthenticated();
    }

    try {
      return await action(session.accessToken);
    } on ApiException catch (error) {
      if (error.statusCode != 401) {
        rethrow;
      }
      final refreshed = await _refreshSession();
      if (refreshed.accessToken.isEmpty) {
        throw ApiException.unauthenticated();
      }
      return action(refreshed.accessToken);
    }
  }

  Future<void> _bootstrap() async {
    final session = await _store.read();
    if (session == null) {
      state = const AuthViewState.ready(session: null);
      return;
    }

    try {
      await _hydrateSession(session);
      return;
    } on ApiException catch (error) {
      if (error.statusCode != 401) {
        state = AuthViewState.ready(
          session: session,
          errorMessage: error.message,
        );
        unawaited(_syncRemoteProfileContext(session));
        return;
      }
    }

    try {
      final refreshed = await _api.refresh(session.refreshToken);
      await _hydrateSession(refreshed);
    } on ApiException {
      await _store.clear();
      state = const AuthViewState.ready(
        session: null,
        errorMessage: 'Your session expired. Please sign in again.',
      );
    }
  }

  Future<void> _submit(Future<AuthSession> Function() perform) async {
    state = state.copyWith(isSubmitting: true, clearError: true);
    try {
      final session = await perform();
      await _hydrateSession(session);
    } on ApiException catch (error) {
      state = state.copyWith(
        initialized: true,
        isSubmitting: false,
        errorMessage: error.message,
      );
      rethrow;
    }
  }

  Future<AuthSession> _refreshSession() async {
    final session = state.session;
    if (session == null) {
      throw ApiException.unauthenticated();
    }

    try {
      final refreshed = await _api.refresh(session.refreshToken);
      return await _hydrateSession(refreshed);
    } on ApiException {
      await _store.clear();
      state = const AuthViewState.ready(session: null);
      throw ApiException.unauthenticated();
    }
  }

  Future<AuthSession> _hydrateSession(AuthSession session) async {
    MobileUser user = session.user;
    try {
      user = await _api.me(session.accessToken);
    } on ApiException catch (error) {
      if (error.statusCode == 401) {
        rethrow;
      }
    }

    final hydrated = session.copyWith(user: user);
    await _store.write(hydrated);
    state = AuthViewState.ready(session: hydrated);
    unawaited(_syncRemoteProfileContext(hydrated));
    return hydrated;
  }

  Future<void> _syncRemoteProfileContext(AuthSession session) async {
    unawaited(PushNotificationService.syncStoredToken());
    try {
      await Future(() async {
        final profile = await _api.getProfile(session.accessToken);
        await _themeController.applyRemoteTheme(profile.themeMode);

        var updatedProfile = profile;
        var changed = false;

        if (updatedProfile.locationMode.toLowerCase() != 'manual') {
          final locationResult = await _locationService
              .captureCurrentLocation()
              .timeout(const Duration(seconds: 10));
          if (locationResult.snapshot != null) {
            final snapshot = locationResult.snapshot!;
            final timezone = _isTimezoneName(snapshot.timezone)
                ? snapshot.timezone
                : updatedProfile.timezone;
            final latChanged =
                updatedProfile.latitude == null ||
                (updatedProfile.latitude! - snapshot.latitude).abs() > 0.0005;
            final lonChanged =
                updatedProfile.longitude == null ||
                (updatedProfile.longitude! - snapshot.longitude).abs() >
                    0.0005;
            final timezoneChanged = timezone != updatedProfile.timezone;
            if (latChanged || lonChanged || timezoneChanged) {
              updatedProfile = updatedProfile.copyWith(
                locationMode: 'auto',
                latitude: snapshot.latitude,
                longitude: snapshot.longitude,
                timezone: timezone,
              );
              changed = true;
            }
          } else if ((locationResult.permissionDenied ||
                  locationResult.serviceDisabled) &&
              updatedProfile.latitude == null &&
              updatedProfile.longitude == null &&
              updatedProfile.locationMode.toLowerCase() != 'manual') {
            updatedProfile = updatedProfile.copyWith(locationMode: 'manual');
            changed = true;
          }
        }

        if (changed) {
          final saved = await _api.updateProfile(
            accessToken: session.accessToken,
            profile: updatedProfile,
          );
          await _themeController.applyRemoteTheme(saved.themeMode);
        }
      }).timeout(const Duration(seconds: 20));
    } on ApiException catch (error) {
      if (error.statusCode == 401) {
        await _store.clear();
        state = const AuthViewState.ready(
          session: null,
          errorMessage: 'Your session expired. Please sign in again.',
        );
      }
    } catch (_) {}
  }

  bool _isTimezoneName(String value) {
    final normalized = value.trim();
    return normalized.contains('/');
  }
}
