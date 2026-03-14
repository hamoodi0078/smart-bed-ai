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

final settingsBundleProvider = FutureProvider<SettingsBundle>((ref) async {
  return ref.read(smartBedRepositoryProvider).loadSettingsBundle();
});

class SmartBedRepository {
  SmartBedRepository(this.ref);

  final Ref ref;

  SmartBedApi get _api => ref.read(smartBedApiProvider);
  AuthController get _auth => ref.read(authControllerProvider.notifier);

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

  Future<SettingsBundle> loadSettingsBundle() async {
    final settings = await _auth.performAuthorized(_api.getSettings);
    final profile = await _auth.performAuthorized(_api.getProfile);
    return SettingsBundle(settings: settings, profile: profile);
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
}
