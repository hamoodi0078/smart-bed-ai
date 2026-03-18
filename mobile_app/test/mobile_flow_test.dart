import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile_app/src/core/models.dart';
import 'package:mobile_app/src/state/auth_controller.dart';
import 'package:mobile_app/src/state/mobile_data.dart';
import 'package:mobile_app/src/ui/screens/auth_screen.dart';
import 'package:mobile_app/src/ui/screens/dashboard_screen.dart';
import 'package:mobile_app/src/ui/screens/launch_screen.dart';
import 'package:mobile_app/src/ui/screens/scenes_screen.dart';
import 'package:mobile_app/src/ui/screens/settings_screen.dart';
import 'package:mobile_app/src/ui/screens/timeline_screen.dart';

void main() {
  testWidgets('launch screen shows Danah branding', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authControllerProvider.overrideWith(_LoadingAuthController.new),
        ],
        child: const MaterialApp(home: LaunchScreen()),
      ),
    );
    await tester.pump();

    expect(find.text('Danah Smart Bed'), findsOneWidget);
    expect(find.text('Built by Dana Abuhalifa'), findsOneWidget);
    expect(find.text('Dana is getting ready'), findsOneWidget);
    expect(find.text('Restoring your Danah session...'), findsOneWidget);

    await tester.pump(const Duration(milliseconds: 1900));
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });

  testWidgets('auth screen switches to create account mode', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authControllerProvider.overrideWith(_UnauthedAuthController.new),
        ],
        child: const MaterialApp(home: AuthScreen()),
      ),
    );
    await tester.pump();

    await tester.tap(find.text('Register'));
    await tester.pump();

    expect(find.text('Full name'), findsOneWidget);
    expect(find.text('Create Danah account'), findsOneWidget);
  });

  testWidgets('dashboard renders the Danah home shell', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authControllerProvider.overrideWith(_ReadyAuthController.new),
          dashboardBundleProvider.overrideWith((ref) async => _dashboardBundle),
          bedStateProvider.overrideWith((ref) async => _bedState),
          islamicOverviewProvider.overrideWith((ref) async => _islamicOverview),
          subscriptionStatusProvider.overrideWith(
            (ref) async => _subscriptionStatus,
          ),
          timelineFeedProvider.overrideWith((ref) async => _timelineItems),
          firstThreeNightsChecklistProvider.overrideWith(
            (ref) async => _checklist,
          ),
          betaMetricsProvider.overrideWith((ref) async => _betaMetrics),
          undoStatusProvider.overrideWith((ref) async => _undoStatus),
        ],
        child: const MaterialApp(home: Scaffold(body: DashboardScreen())),
      ),
    );
    await tester.pump();
    await tester.pump();

    expect(find.textContaining('Hamoud'), findsOneWidget);
    expect(find.text('Dana is live. Your prayer timings, routines, and bed controls are synced for Karachi, Pakistan.'), findsOneWidget);
    expect(find.text('Next prayer'), findsOneWidget);
    expect(find.text('Tonight at a glance'), findsOneWidget);
    expect(find.text('Account momentum'), findsOneWidget);
    expect(find.text('Dana insight'), findsOneWidget);
    expect(find.text('Start wind-down'), findsOneWidget);
    expect(find.text('3D bed view'), findsOneWidget);
    expect(find.text('Dana Live'), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });

  testWidgets('scenes preview calls repository preview API method', (
    tester,
  ) async {
    late _FakeSmartBedRepository repo;
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authControllerProvider.overrideWith(_ReadyAuthController.new),
          smartBedRepositoryProvider.overrideWith((ref) {
            repo = _FakeSmartBedRepository(ref);
            return repo;
          }),
          sceneGalleryProvider.overrideWith((ref) async => _sceneGallery),
          dashboardBundleProvider.overrideWith((ref) async => _dashboardBundle),
        ],
        child: const MaterialApp(home: Scaffold(body: ScenesScreen())),
      ),
    );
    await tester.pump();

    await tester.tap(find.text('Preview').first);
    await tester.pump();

    expect(find.text('Open 3D viewer'), findsOneWidget);
    expect(repo.previewSceneCalls, 1);
    expect(repo.lastPreviewSceneKey, 'wind_down');
  });

  testWidgets('timeline marks timeline-review checklist step', (tester) async {
    late _FakeSmartBedRepository repo;
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authControllerProvider.overrideWith(_ReadyAuthController.new),
          smartBedRepositoryProvider.overrideWith((ref) {
            repo = _FakeSmartBedRepository(ref);
            return repo;
          }),
          timelineFeedProvider.overrideWith((ref) async => _timelineItems),
          dashboardBundleProvider.overrideWith((ref) async => _dashboardBundle),
          firstThreeNightsChecklistProvider.overrideWith(
            (ref) async => _checklist,
          ),
          betaMetricsProvider.overrideWith((ref) async => _betaMetrics),
        ],
        child: const MaterialApp(home: Scaffold(body: TimelineScreen())),
      ),
    );
    await tester.pump();

    expect(find.text('Pattern insight'), findsOneWidget);
    expect(find.text('1 wind-down event(s)'), findsOneWidget);
    expect(repo.timelineReviewCalls, 1);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
  });

  testWidgets('settings save persists edited profile and settings', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1200, 1800));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    _FakeSmartBedRepository? repo;
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authControllerProvider.overrideWith(_ReadyAuthController.new),
          smartBedRepositoryProvider.overrideWith((ref) {
            final value = _FakeSmartBedRepository(ref);
            repo = value;
            return value;
          }),
          settingsBundleProvider.overrideWith((ref) async => _settingsBundle),
          subscriptionStatusProvider.overrideWith(
            (ref) async => _subscriptionStatus,
          ),
        ],
        child: const MaterialApp(home: Scaffold(body: SettingsScreen())),
      ),
    );
    await tester.pump();
    await tester.pump();

    await tester.enterText(find.byType(TextField).first, 'Hamoud Prime');
    await tester.pump();

    await tester.ensureVisible(find.text('Save settings'));
    await tester.pump();
    await tester.tap(find.text('Save settings'), warnIfMissed: false);
    await tester.pump();

    expect(repo, isNotNull);
    expect(repo!.saveSettingsCalls, 1);
    expect(
      repo!.lastSavedBundle?.profile.displayName,
      'Hamoud Prime',
    );
  });
}

class _LoadingAuthController extends AuthController {
  @override
  AuthViewState build() => const AuthViewState.loading();
}

class _UnauthedAuthController extends AuthController {
  @override
  AuthViewState build() => const AuthViewState.ready(session: null);
}

class _ReadyAuthController extends AuthController {
  @override
  AuthViewState build() {
    return const AuthViewState.ready(
      session: AuthSession(
        accessToken: 'access-token',
        refreshToken: 'refresh-token',
        user: MobileUser(
          userId: 'u1',
          email: 'hamoud@example.com',
          name: 'Hamoud',
          clientName: 'Hamoud',
        ),
      ),
    );
  }

  @override
  Future<void> signOut() async {
    state = const AuthViewState.ready(session: null);
  }
}

class _FakeSmartBedRepository extends SmartBedRepository {
  _FakeSmartBedRepository(super.ref);

  int previewSceneCalls = 0;
  int timelineReviewCalls = 0;
  int saveSettingsCalls = 0;
  String lastPreviewSceneKey = '';
  SettingsBundle? lastSavedBundle;

  @override
  Future<ScenePreviewResult> previewScene(String sceneKey) async {
    previewSceneCalls += 1;
    lastPreviewSceneKey = sceneKey;
    return const ScenePreviewResult(
      sceneKey: 'wind_down',
      sceneLabel: 'Wind Down',
      previewDurationSeconds: 3,
      elapsedSeconds: 3,
      message: 'Preview complete.',
      traceId: 'req_deadbeef',
    );
  }

  @override
  Future<SceneSaveResult> saveSceneForTonight(String sceneKey) async {
    return const SceneSaveResult(
      sceneKey: 'wind_down',
      sceneLabel: 'Wind Down',
      message: 'Scene saved for tonight.',
      traceId: 'req_deadbeef',
    );
  }

  @override
  Future<FirstThreeNightsChecklist> completeFirstThreeNightsStep(
    String stepKey,
  ) async {
    timelineReviewCalls += 1;
    return _checklist;
  }

  @override
  Future<SettingsBundle> saveSettingsBundle({
    required UserSettings settings,
    required UserProfilePrefs profile,
  }) async {
    saveSettingsCalls += 1;
    lastSavedBundle = SettingsBundle(settings: settings, profile: profile);
    return lastSavedBundle!;
  }
}

const _checklist = FirstThreeNightsChecklist(
  title: 'First 3 Nights',
  completedSteps: 2,
  totalSteps: 5,
  progressPct: 40,
  isComplete: false,
  nextStepKey: 'first_winddown',
  steps: <ChecklistStep>[
    ChecklistStep(
      key: 'signup',
      label: 'Create mobile access',
      description: '',
      completed: true,
      completedAtUtc: '2026-03-14T00:00:00Z',
    ),
    ChecklistStep(
      key: 'first_scene_preview',
      label: 'Preview first scene',
      description: '',
      completed: true,
      completedAtUtc: '2026-03-14T00:00:00Z',
    ),
  ],
);

const _betaMetrics = BetaMetrics(
  windowDays: 7,
  activationProgressPct: 60,
  first3NightsCompleted: 3,
  first3NightsTotal: 5,
  commandTotal7d: 4,
  commandCompletionRatePct: 75,
  windDownSessions7d: 2,
  nightlyFeedbackTotal: 1,
  nightlyFeedbackHelpfulPct: 100,
  automationFeedbackTotal: 1,
  automationFeedbackHelpfulPct: 100,
  cohortStatusLine: 'Activation is moving.',
  qualityGateLine: 'Reliability is stable.',
  generatedAtUtc: '2026-03-14T00:00:00Z',
);

const _undoStatus = UndoStatus(
  canUndo: true,
  actionType: 'device_command',
  secondsRemaining: 8,
);

const _bedState = BedStateSnapshot(
  schemaVersion: '2.0',
  capabilities: <String>['lighting', 'wind_down'],
  updatedAt: '2026-03-14T10:00:00Z',
  stale: false,
  deviceOnline: true,
  source: 'device',
  emotionState: 'calm',
  activePersonality: 'guide',
  biometricSummary: <String, dynamic>{},
  deviceHealthStatus: <String, dynamic>{},
);

const _timelineItems = <TimelineItem>[
  TimelineItem(
    time: 'Now',
    event: 'Wind-down routine armed',
    status: 'completed',
    commandId: 'cmd_1',
  ),
  TimelineItem(
    time: 'Now',
    event: 'Quiet hours is active',
    status: 'quiet',
    commandId: '',
  ),
];

const _sceneGallery = SceneGallery(
  previewDurationSeconds: 3,
  items: <SceneItem>[
    SceneItem(
      sceneKey: 'wind_down',
      label: 'Wind Down',
      summary: 'Prepare a calm bedtime transition.',
      previewSeconds: 3,
    ),
  ],
);

const _settingsBundle = SettingsBundle(
  settings: UserSettings(
    responseStyle: 'balanced',
    engagementLevel: 'high',
    partnerModeEnabled: false,
    windDownMinutes: 45,
  ),
  profile: UserProfilePrefs(
    displayName: 'Hamoud',
    timezone: 'Asia/Kuwait',
    pushEnabled: true,
    emailEnabled: false,
    locationMode: 'auto',
    countryCode: 'PK',
    city: 'Karachi',
    latitude: 24.8607,
    longitude: 67.0011,
    themeMode: 'system',
  ),
);

const _dashboardBundle = DashboardBundle(
  dashboard: DashboardSummary(
    name: 'Hamoud',
    location: 'Kuwait',
    responseStyle: 'balanced',
    engagementLevel: 'high',
    partnerModeEnabled: false,
    windDownMinutes: 45,
    lastCommandResult: CommandResult(
      commandId: 'cmd_1',
      action: 'winddown',
      summary: 'Wind-down started.',
      status: 'completed',
      success: true,
      timestampUtc: '2026-03-14T00:00:00Z',
      traceId: 'req_deadbeef',
      retryAction: '',
      diagnostic: 'All good.',
    ),
    bedtimeDriftAlert: 'Bedtime drift is rising by 20 minutes this week.',
    weeklyInsight: WeeklyInsight(
      windowDays: 7,
      windDownSessions: 2,
      completedActions: 3,
      automationActions: 4,
      quietOverrides: 1,
      completionRatePct: 75,
      feedbackTotalVotes: 3,
      feedbackHelpfulPct: 67,
      trend: 'attention',
      headline: '2 wind-down session(s) completed this week',
      summary: 'Consistency is building.',
    ),
    nightlySummary: NightlySummary(
      headline: "Tonight's sleep summary",
      trendTitle: 'Steady progress',
      focusLine: 'Wind-down completed tonight.',
      sleepQualityLine: 'Sleep quality trend is improving.',
      consistencyLine: 'Bedtime consistency is stabilizing.',
      recoveryPlanLine: 'Keep the same bedtime target tomorrow.',
      generatedAtUtc: '2026-03-14T00:00:00Z',
    ),
    firstThreeNightsChecklist: _checklist,
    nightlySummaryFeedback: NightlySummaryFeedback(
      helpfulCount: 1,
      notHelpfulCount: 0,
      totalVotes: 1,
      helpfulPct: 100,
      lastVote: 'helpful',
      lastVoteAtUtc: '2026-03-14T00:00:00Z',
    ),
    automationFeedbackLoop: AutomationFeedbackLoop(
      helpfulCount: 1,
      notHelpfulCount: 0,
      totalVotes: 1,
      helpfulPct: 100,
      lastVote: 'helpful',
      lastVoteAtUtc: '2026-03-14T00:00:00Z',
      lastCommandId: 'cmd_1',
      lastCommandAction: 'winddown',
      statusLine: 'Automation feedback is strong. Keep repeating this routine.',
    ),
  ),
  trialStatus: TrialStatus(
    subscriptionStatus: 'free',
    trialActive: false,
    trialDaysRemaining: null,
    trialEndDate: '',
    features: <String, int>{'max_scenes': 3, 'wind_down_minutes': 10},
  ),
);

const _islamicOverview = IslamicOverview(
  prayers: <String, String>{
    'Fajr': '05:21',
    'Dhuhr': '12:33',
    'Asr': '16:08',
    'Maghrib': '18:27',
    'Isha': '19:42',
  },
  nextPrayer: PrayerCountdown(
    name: 'Isha',
    time: '19:42',
    minutesUntil: 37,
  ),
  location: PrayerLocation(
    mode: 'auto',
    city: 'Karachi',
    countryCode: 'PK',
    countryName: 'Pakistan',
    timezone: 'Asia/Karachi',
    latitude: 24.8607,
    longitude: 67.0011,
    label: 'Karachi, Pakistan',
  ),
  hadith: <String, dynamic>{
    'hadith': 'Actions are judged by intentions.',
    'source': 'Sahih Bukhari',
  },
  sleepHadith: <String, dynamic>{
    'hadith': 'Recite the evening remembrance before sleep.',
  },
  hijri: <String, dynamic>{
    'hijri_date': '15 Ramadan 1447',
  },
  islamicEvent: 'Ramadan Kareem',
  ramadanActive: true,
  sunnahTip: 'Sleep on your right side as the Prophet recommended.',
  ledColor: '#7B68EE',
);

const _subscriptionStatus = SubscriptionStatus(
  subscriptionStatus: 'premium',
  trialActive: false,
  trialDaysRemaining: null,
  trialEndDate: '',
  planTier: 'premium',
  billingInterval: 'monthly',
  paymentProvider: 'paypal',
  priceKwd: 4.9,
  status: 'active',
  nextRenewalAt: '2026-04-14T00:00:00Z',
  graceEndAt: '',
  providerSubscriptionId: 'I-DEMO123',
  providerPlanId: 'P-DEMO456',
  providerStatus: 'ACTIVE',
  startedAt: '2026-03-14T00:00:00Z',
  lastPaymentAt: '2026-03-14T00:00:00Z',
  cancelledAt: '',
);
