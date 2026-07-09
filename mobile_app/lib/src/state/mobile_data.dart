import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/api_client.dart';
import '../core/models.dart';
import 'auth_controller.dart';

final smartBedRepositoryProvider = Provider<SmartBedRepository>(
  SmartBedRepository.new,
);

final bedStateProvider = FutureProvider<BedStateSnapshot>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadBedState();
});

final dashboardBundleProvider = FutureProvider<DashboardBundle>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadDashboardBundle();
});

final sceneGalleryProvider = FutureProvider<SceneGallery>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadScenes();
});

final timelineFeedProvider = FutureProvider<List<TimelineItem>>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadTimeline();
});

final firstThreeNightsChecklistProvider =
    FutureProvider<FirstThreeNightsChecklist>((ref) async {
      return ref
          .read(smartBedRepositoryProvider)
          .loadFirstThreeNightsChecklist();
    });

final betaMetricsProvider = FutureProvider<BetaMetrics>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadBetaMetrics();
});

final undoStatusProvider = FutureProvider<UndoStatus>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadUndoStatus();
});

final settingsBundleProvider = FutureProvider<SettingsBundle>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadSettingsBundle();
});

final islamicOverviewProvider = FutureProvider<IslamicOverview>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadIslamicOverview();
});

final subscriptionStatusProvider = FutureProvider<SubscriptionStatus>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadSubscriptionStatus();
});

final subscriptionHistoryProvider =
    FutureProvider<List<BillingHistoryEvent>>((ref) async {
      return ref.read(smartBedRepositoryProvider).loadSubscriptionHistory();
    });

final deviceControlsProvider = FutureProvider<DeviceControls>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadDeviceControls();
});

final bedPairingStatusProvider = FutureProvider<BedPairingStatus>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadBedPairingStatus();
});

final alarmsProvider = FutureProvider<List<AlarmSchedule>>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadAlarms();
});

final spotifyStatusProvider = FutureProvider<SpotifyConnectionStatus>((
  ref,
) async {
  return ref.read(smartBedRepositoryProvider).loadSpotifyStatus();
});

final spotifyPlaybackStatusProvider = FutureProvider<SpotifyPlaybackStatus>((
  ref,
) async {
  return ref.read(smartBedRepositoryProvider).loadSpotifyPlaybackStatus();
});

final mobileDeviceInfoProvider = FutureProvider<MobileDeviceInfo>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadMobileDeviceInfo();
});

final achievementsProvider = FutureProvider<Map<String, dynamic>>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadAchievements();
});

class SmartBedRepository {
  SmartBedRepository(this.ref);

  final Ref ref;

  SmartBedApi get _api => ref.read(smartBedApiProvider);
  AuthController get _auth => ref.read(authControllerProvider.notifier);

  String get apiBaseUrl => _api.baseUrl;

  MobileUser get _currentUser {
    final user = ref.read(authControllerProvider).session?.user;
    if (user == null) {
      throw ApiException.unauthenticated();
    }
    return user;
  }

  Future<BedStateSnapshot> loadBedState() {
    return _auth.performAuthorized(_api.getBedState);
  }

  Future<DashboardBundle> loadDashboardBundle() async {
    final user = _currentUser;
    final dashboard = await _auth.performAuthorized(_api.getDashboard);
    final trial = await _auth.performAuthorized(
      (accessToken) =>
          _api.getTrialStatus(userId: user.userId, accessToken: accessToken),
    );
    return DashboardBundle(dashboard: dashboard, trialStatus: trial);
  }

  Future<SceneGallery> loadScenes() {
    return _auth.performAuthorized(_api.getScenes);
  }

  Future<List<TimelineItem>> loadTimeline() {
    return _auth.performAuthorized(_api.getTimeline);
  }

  Future<FirstThreeNightsChecklist> loadFirstThreeNightsChecklist() {
    return _auth.performAuthorized(_api.getFirstThreeNightsChecklist);
  }

  Future<FirstThreeNightsChecklist> completeFirstThreeNightsStep(
    String stepKey,
  ) {
    return _auth.performAuthorized(
      (accessToken) => _api.completeFirstThreeNightsStep(
        accessToken: accessToken,
        stepKey: stepKey,
      ),
    );
  }

  Future<NightlySummaryFeedback> submitNightlySummaryFeedback({
    required String vote,
    String summaryGeneratedAtUtc = '',
  }) {
    return _auth.performAuthorized(
      (accessToken) => _api.submitNightlySummaryFeedback(
        accessToken: accessToken,
        vote: vote,
        summaryGeneratedAtUtc: summaryGeneratedAtUtc,
      ),
    );
  }

  Future<AutomationFeedbackLoop> submitCommandFeedback({
    required String commandId,
    required String vote,
    String note = '',
  }) {
    return _auth.performAuthorized(
      (accessToken) => _api.submitCommandFeedback(
        accessToken: accessToken,
        commandId: commandId,
        vote: vote,
        note: note,
      ),
    );
  }

  Future<BetaMetrics> loadBetaMetrics() {
    return _auth.performAuthorized(_api.getBetaMetrics);
  }

  Future<UndoStatus> loadUndoStatus() {
    return _auth.performAuthorized(_api.getUndoStatus);
  }

  Future<UndoResult> undoLastAction() {
    return _auth.performAuthorized(_api.undoLastAction);
  }

  Future<SettingsBundle> loadSettingsBundle() async {
    final settings = await _auth.performAuthorized(_api.getSettings);
    final profile = await _auth.performAuthorized(_api.getProfile);
    return SettingsBundle(settings: settings, profile: profile);
  }

  Future<IslamicOverview> loadIslamicOverview() {
    return _auth.performAuthorized(_api.getIslamicOverview);
  }

  Future<String> sendChatMessage(String message) {
    return _auth.performAuthorized(
      (accessToken) =>
          _api.sendChatMessage(accessToken: accessToken, message: message),
    );
  }

  Future<SubscriptionStatus> loadSubscriptionStatus() {
    return _auth.performAuthorized(_api.getSubscriptionStatus);
  }

  Future<List<BillingHistoryEvent>> loadSubscriptionHistory({int limit = 12}) {
    return _auth.performAuthorized(
      (accessToken) => _api.getSubscriptionHistory(accessToken, limit: limit),
    );
  }

  Future<CheckoutSessionInfo> startSubscriptionCheckout({
    required String tier,
    required String interval,
    String returnUrl = '',
    String cancelUrl = '',
  }) {
    return _auth.performAuthorized(
      (accessToken) => _api.createSubscriptionCheckout(
        accessToken: accessToken,
        tier: tier,
        interval: interval,
        returnUrl: returnUrl,
        cancelUrl: cancelUrl,
      ),
    );
  }

  Future<String> pauseActiveSubscription({String reason = ''}) {
    return _auth.performAuthorized(
      (accessToken) => _api.pauseActiveSubscription(
        accessToken: accessToken,
        reason: reason,
      ),
    );
  }

  Future<String> cancelActiveSubscription({String reason = ''}) {
    return _auth.performAuthorized(
      (accessToken) => _api.cancelActiveSubscription(
        accessToken: accessToken,
        reason: reason,
      ),
    );
  }

  Future<DeviceCommandReceipt> sendDeviceCommand(String action) {
    return _auth.performAuthorized(
      (accessToken) =>
          _api.createDeviceCommand(accessToken: accessToken, action: action),
    );
  }

  Future<ScenePreviewResult> previewScene(String sceneKey) {
    return _auth.performAuthorized(
      (accessToken) =>
          _api.previewScene(accessToken: accessToken, sceneKey: sceneKey),
    );
  }

  Future<SceneSaveResult> saveSceneForTonight(String sceneKey) {
    return _auth.performAuthorized(
      (accessToken) => _api.saveSceneForTonight(
        accessToken: accessToken,
        sceneKey: sceneKey,
      ),
    );
  }

  Future<TrialStatus> startTrial() {
    final user = _currentUser;
    return _auth.performAuthorized(
      (accessToken) =>
          _api.startTrial(userId: user.userId, accessToken: accessToken),
    );
  }

  Future<SettingsBundle> saveSettingsBundle({
    required UserSettings settings,
    required UserProfilePrefs profile,
  }) async {
    final updatedSettings = await _auth.performAuthorized(
      (accessToken) =>
          _api.updateSettings(accessToken: accessToken, settings: settings),
    );
    final updatedProfile = await _auth.performAuthorized(
      (accessToken) =>
          _api.updateProfile(accessToken: accessToken, profile: profile),
    );
    return SettingsBundle(settings: updatedSettings, profile: updatedProfile);
  }

  Future<DeviceControls> loadDeviceControls() {
    return _auth.performAuthorized(_api.getDeviceControls);
  }

  Future<DeviceControls> saveDeviceControls(DeviceControls controls) {
    return _auth.performAuthorized(
      (accessToken) =>
          _api.updateDeviceControls(accessToken: accessToken, controls: controls),
    );
  }

  Future<BedPairingStatus> loadBedPairingStatus() {
    return _auth.performAuthorized(_api.getBedPairingStatus);
  }

  Future<BedPairingStatus> pairBed({
    String qrPayload = '',
    String deviceId = '',
    String claimToken = '',
    String bedLocation = 'Kuwait',
  }) {
    return _auth.performAuthorized(
      (accessToken) => _api.pairBed(
        accessToken: accessToken,
        qrPayload: qrPayload,
        deviceId: deviceId,
        claimToken: claimToken,
        bedLocation: bedLocation,
      ),
    );
  }

  Future<void> unpairBed({String deviceId = ''}) {
    return _auth.performAuthorized(
      (accessToken) => _api.unpairBed(
        accessToken: accessToken,
        deviceId: deviceId,
      ),
    );
  }

  Future<List<AlarmSchedule>> loadAlarms() {
    return _auth.performAuthorized(_api.getAlarms);
  }

  Future<List<AlarmSchedule>> saveAlarm(AlarmSchedule alarm) {
    return _auth.performAuthorized(
      (accessToken) => _api.upsertAlarm(
        accessToken: accessToken,
        alarm: alarm,
      ),
    );
  }

  Future<void> toggleAlarm({
    required String alarmId,
    required bool enabled,
  }) {
    return _auth.performAuthorized(
      (accessToken) => _api.toggleAlarm(
        accessToken: accessToken,
        alarmId: alarmId,
        enabled: enabled,
      ),
    );
  }

  Future<void> deleteAlarm(String alarmId) {
    return _auth.performAuthorized(
      (accessToken) => _api.deleteAlarm(
        accessToken: accessToken,
        alarmId: alarmId,
      ),
    );
  }

  Future<String> spotifyAuthUrl({String doneUri = ''}) {
    return _auth.performAuthorized(
      (accessToken) => _api.getSpotifyAuthUrl(
        accessToken: accessToken,
        doneUri: doneUri,
      ),
    );
  }

  Future<SpotifyConnectionStatus> loadSpotifyStatus() {
    return _auth.performAuthorized(_api.getSpotifyStatus);
  }

  Future<SpotifyPlaybackStatus> loadSpotifyPlaybackStatus() {
    return _auth.performAuthorized(_api.getSpotifyPlaybackStatus);
  }

  Future<String> spotifyPlaybackAction({
    required String action,
    String deviceId = '',
    String playlistUri = '',
    int volumePercent = 50,
  }) {
    return _auth.performAuthorized(
      (accessToken) => _api.spotifyPlaybackAction(
        accessToken: accessToken,
        action: action,
        deviceId: deviceId,
        playlistUri: playlistUri,
        volumePercent: volumePercent,
      ),
    );
  }

  Future<void> disconnectSpotify() {
    return _auth.performAuthorized(
      (accessToken) => _api.disconnectSpotify(accessToken: accessToken),
    );
  }

  Future<MobileDeviceInfo> loadMobileDeviceInfo() {
    return _auth.performAuthorized(_api.getMobileDeviceInfo);
  }

  Future<Map<String, dynamic>> loadAchievements() {
    return _auth.performAuthorized(_api.getAchievements);
  }
}
