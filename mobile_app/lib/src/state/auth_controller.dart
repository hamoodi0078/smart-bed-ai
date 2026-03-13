import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/models.dart';
import '../core/session_store.dart';

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
      final user = await _api.me(session.accessToken);
      final refreshed = session.copyWith(user: user);
      await _store.write(refreshed);
      state = AuthViewState.ready(session: refreshed);
      return;
    } on ApiException catch (error) {
      if (error.statusCode != 401) {
        state = AuthViewState.ready(
          session: session,
          errorMessage: error.message,
        );
        return;
      }
    }

    try {
      final refreshed = await _api.refresh(session.refreshToken);
      await _store.write(refreshed);
      state = AuthViewState.ready(session: refreshed);
    } on ApiException {
      await _store.clear();
      state = const AuthViewState.ready(session: null);
    }
  }

  Future<void> _submit(Future<AuthSession> Function() perform) async {
    state = state.copyWith(isSubmitting: true, clearError: true);
    try {
      final session = await perform();
      await _store.write(session);
      state = AuthViewState.ready(session: session);
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
      await _store.write(refreshed);
      state = state.copyWith(
        initialized: true,
        isSubmitting: false,
        session: refreshed,
        clearError: true,
      );
      return refreshed;
    } on ApiException {
      await _store.clear();
      state = const AuthViewState.ready(session: null);
      throw ApiException.unauthenticated();
    }
  }
}
