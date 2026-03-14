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
  testWidgets('launch screen shows Danah Abuhalifa branding', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authControllerProvider.overrideWith(_LoadingAuthController.new),
        ],
        child: const MaterialApp(home: LaunchScreen()),
      ),
    );
    await tester.pump();

    expect(find.text('Smart Bed'), findsOneWidget);
    expect(find.text('Danah Abuhalifa'), findsOneWidget);
    expect(find.text('Smart Living, Smart Sleep'), findsOneWidget);
    expect(
      find.text('Warming up your calm command center...'),
      findsOneWidget,
    );

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

    await tester.tap(find.text('Create Account'));
    await tester.pump();

    expect(find.text('Name'), findsOneWidget);
    expect(find.text('Create Mobile Access'), findsOneWidget);
  });

  testWidgets('dashboard renders command-center milestone cards', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          authControllerProvider.overrideWith(_ReadyAuthController.new),
          dashboardBundleProvider.overrideWith((ref) async => _dashboardBundle),
          bedStateProvider.overrideWith((ref) async => _bedState),
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

    expect(find.text('Command Center'), findsOneWidget);
    expect(find.text('Quick actions'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.text('Was this nightly summary helpful?'),
      300,
    );
    expect(find.text('Was this nightly summary helpful?'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Beta metrics'), 300);
    expect(find.text('Beta metrics'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Undo Last Action'), 300);
    expect(find.text('Undo Last Action'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Start 7-day trial'), 300);
    expect(find.text('Start 7-day trial'), findsOneWidget);

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
        ],
        child: const MaterialApp(home: Scaffold(body: SettingsScreen())),
      ),
    );
    await tester.pump();
    await tester.pump();

    await tester.enterText(
      find.widgetWithText(TextField, 'Display name'),
      'Hamoud Prime',
    );
    await tester.pump();

    await tester.ensureVisible(find.text('Save changes'));
    await tester.pump();
    await tester.tap(find.text('Save changes'), warnIfMissed: false);
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
