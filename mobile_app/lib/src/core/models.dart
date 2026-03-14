Map<String, dynamic> _mapOf(Object? value) {
  if (value is Map<String, dynamic>) {
    return value;
  }
  if (value is Map) {
    return value.map((key, item) => MapEntry(key.toString(), item));
  }
  return <String, dynamic>{};
}

List<Map<String, dynamic>> _mapListOf(Object? value) {
  if (value is! List) {
    return const <Map<String, dynamic>>[];
  }
  return value.map((item) => _mapOf(item)).toList(growable: false);
}

String _stringOf(Object? value, [String fallback = '']) {
  final stringValue = value?.toString().trim() ?? '';
  return stringValue.isEmpty ? fallback : stringValue;
}

int _intOf(Object? value, [int fallback = 0]) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.toInt();
  }
  return int.tryParse(_stringOf(value)) ?? fallback;
}

double _doubleOf(Object? value, [double fallback = 0]) {
  if (value is double) {
    return value;
  }
  if (value is num) {
    return value.toDouble();
  }
  return double.tryParse(_stringOf(value)) ?? fallback;
}

bool _boolOf(Object? value, [bool fallback = false]) {
  if (value is bool) {
    return value;
  }
  final normalized = _stringOf(value).toLowerCase();
  if (normalized == 'true' || normalized == '1') {
    return true;
  }
  if (normalized == 'false' || normalized == '0') {
    return false;
  }
  return fallback;
}

class MobileUser {
  const MobileUser({
    required this.userId,
    required this.email,
    required this.name,
    required this.clientName,
  });

  final String userId;
  final String email;
  final String name;
  final String clientName;

  String get displayName {
    if (clientName.isNotEmpty) {
      return clientName;
    }
    if (name.isNotEmpty) {
      return name;
    }
    return email.split('@').first;
  }

  factory MobileUser.fromJson(Map<String, dynamic> json) {
    return MobileUser(
      userId: _stringOf(json['user_id']),
      email: _stringOf(json['email']),
      name: _stringOf(json['name']),
      clientName: _stringOf(json['client_name']),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'user_id': userId,
      'email': email,
      'name': name,
      'client_name': clientName,
    };
  }
}

class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
    required this.user,
  });

  final String accessToken;
  final String refreshToken;
  final MobileUser user;

  AuthSession copyWith({
    String? accessToken,
    String? refreshToken,
    MobileUser? user,
  }) {
    return AuthSession(
      accessToken: accessToken ?? this.accessToken,
      refreshToken: refreshToken ?? this.refreshToken,
      user: user ?? this.user,
    );
  }

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      accessToken: _stringOf(json['access_token']),
      refreshToken: _stringOf(json['refresh_token']),
      user: MobileUser.fromJson(_mapOf(json['user'])),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'access_token': accessToken,
      'refresh_token': refreshToken,
      'user': user.toJson(),
    };
  }
}

class CommandResult {
  const CommandResult({
    required this.commandId,
    required this.action,
    required this.summary,
    required this.status,
    required this.success,
    required this.timestampUtc,
    required this.traceId,
    required this.retryAction,
    required this.diagnostic,
  });

  final String commandId;
  final String action;
  final String summary;
  final String status;
  final bool success;
  final String timestampUtc;
  final String traceId;
  final String retryAction;
  final String diagnostic;

  bool get hasTrace => traceId.isNotEmpty;

  factory CommandResult.fromJson(Map<String, dynamic> json) {
    return CommandResult(
      commandId: _stringOf(json['command_id']),
      action: _stringOf(json['action']),
      summary: _stringOf(json['summary'], 'Command action'),
      status: _stringOf(json['status'], 'queued'),
      success: _boolOf(json['success']),
      timestampUtc: _stringOf(json['timestamp_utc']),
      traceId: _stringOf(json['trace_id']),
      retryAction: _stringOf(json['retry_action']),
      diagnostic: _stringOf(json['diagnostic']),
    );
  }
}

class DashboardSummary {
  const DashboardSummary({
    required this.name,
    required this.location,
    required this.responseStyle,
    required this.engagementLevel,
    required this.partnerModeEnabled,
    required this.windDownMinutes,
    required this.lastCommandResult,
    required this.bedtimeDriftAlert,
    required this.weeklyInsight,
    required this.nightlySummary,
    required this.firstThreeNightsChecklist,
    required this.nightlySummaryFeedback,
    required this.automationFeedbackLoop,
  });

  final String name;
  final String location;
  final String responseStyle;
  final String engagementLevel;
  final bool partnerModeEnabled;
  final int windDownMinutes;
  final CommandResult? lastCommandResult;
  final String bedtimeDriftAlert;
  final WeeklyInsight weeklyInsight;
  final NightlySummary nightlySummary;
  final FirstThreeNightsChecklist firstThreeNightsChecklist;
  final NightlySummaryFeedback nightlySummaryFeedback;
  final AutomationFeedbackLoop automationFeedbackLoop;

  factory DashboardSummary.fromJson(Map<String, dynamic> json) {
    final rawCommand = _mapOf(json['last_command_result']);
    return DashboardSummary(
      name: _stringOf(json['name'], 'Guest'),
      location: _stringOf(json['location'], 'Kuwait'),
      responseStyle: _stringOf(json['response_style'], 'balanced'),
      engagementLevel: _stringOf(json['engagement_level'], 'high'),
      partnerModeEnabled: _boolOf(json['partner_mode_enabled']),
      windDownMinutes: _intOf(json['wind_down_minutes'], 45),
      lastCommandResult: rawCommand.isEmpty
          ? null
          : CommandResult.fromJson(rawCommand),
      bedtimeDriftAlert: _stringOf(json['bedtime_drift_alert']),
      weeklyInsight: WeeklyInsight.fromJson(_mapOf(json['weekly_insight'])),
      nightlySummary: NightlySummary.fromJson(_mapOf(json['nightly_summary'])),
      firstThreeNightsChecklist: FirstThreeNightsChecklist.fromJson(
        _mapOf(json['first_3_nights_checklist']),
      ),
      nightlySummaryFeedback: NightlySummaryFeedback.fromJson(
        _mapOf(json['nightly_summary_feedback']),
      ),
      automationFeedbackLoop: AutomationFeedbackLoop.fromJson(
        _mapOf(json['automation_feedback_loop']),
      ),
    );
  }
}

class WeeklyInsight {
  const WeeklyInsight({
    required this.windowDays,
    required this.windDownSessions,
    required this.completedActions,
    required this.automationActions,
    required this.quietOverrides,
    required this.completionRatePct,
    required this.trend,
    required this.headline,
    required this.summary,
  });

  final int windowDays;
  final int windDownSessions;
  final int completedActions;
  final int automationActions;
  final int quietOverrides;
  final int completionRatePct;
  final String trend;
  final String headline;
  final String summary;

  bool get hasActivity => automationActions > 0 || windDownSessions > 0;

  factory WeeklyInsight.fromJson(Map<String, dynamic> json) {
    return WeeklyInsight(
      windowDays: _intOf(json['window_days'], 7),
      windDownSessions: _intOf(json['wind_down_sessions'], 0),
      completedActions: _intOf(json['completed_actions'], 0),
      automationActions: _intOf(json['automation_actions'], 0),
      quietOverrides: _intOf(json['quiet_overrides'], 0),
      completionRatePct: _intOf(json['completion_rate_pct'], 0),
      trend: _stringOf(json['trend'], 'steady'),
      headline: _stringOf(
        json['headline'],
        'Your weekly sleep insight will appear after your first actions.',
      ),
      summary: _stringOf(
        json['summary'],
        'Trigger wind-down tonight to start the habit loop.',
      ),
    );
  }
}

class NightlySummary {
  const NightlySummary({
    required this.headline,
    required this.trendTitle,
    required this.focusLine,
    required this.sleepQualityLine,
    required this.consistencyLine,
    required this.recoveryPlanLine,
    required this.generatedAtUtc,
  });

  final String headline;
  final String trendTitle;
  final String focusLine;
  final String sleepQualityLine;
  final String consistencyLine;
  final String recoveryPlanLine;
  final String generatedAtUtc;

  factory NightlySummary.fromJson(Map<String, dynamic> json) {
    return NightlySummary(
      headline: _stringOf(json['headline'], "Tonight's sleep summary"),
      trendTitle: _stringOf(json['trend_title'], 'Steady progress'),
      focusLine: _stringOf(
        json['focus_line'],
        'No command executed yet tonight.',
      ),
      sleepQualityLine: _stringOf(
        json['sleep_quality_line'],
        'Sleep quality score is still collecting data.',
      ),
      consistencyLine: _stringOf(
        json['consistency_line'],
        'Consistency score is still collecting data.',
      ),
      recoveryPlanLine: _stringOf(
        json['recovery_plan_line'],
        'No recovery plan yet.',
      ),
      generatedAtUtc: _stringOf(json['generated_at_utc']),
    );
  }
}

class ChecklistStep {
  const ChecklistStep({
    required this.key,
    required this.label,
    required this.description,
    required this.completed,
    required this.completedAtUtc,
  });

  final String key;
  final String label;
  final String description;
  final bool completed;
  final String completedAtUtc;

  factory ChecklistStep.fromJson(Map<String, dynamic> json) {
    return ChecklistStep(
      key: _stringOf(json['key']),
      label: _stringOf(json['label'], 'Step'),
      description: _stringOf(json['description']),
      completed: _boolOf(json['completed']),
      completedAtUtc: _stringOf(json['completed_at_utc']),
    );
  }
}

class FirstThreeNightsChecklist {
  const FirstThreeNightsChecklist({
    required this.title,
    required this.completedSteps,
    required this.totalSteps,
    required this.progressPct,
    required this.isComplete,
    required this.nextStepKey,
    required this.steps,
  });

  final String title;
  final int completedSteps;
  final int totalSteps;
  final int progressPct;
  final bool isComplete;
  final String nextStepKey;
  final List<ChecklistStep> steps;

  factory FirstThreeNightsChecklist.fromJson(Map<String, dynamic> json) {
    return FirstThreeNightsChecklist(
      title: _stringOf(json['title'], 'First 3 Nights'),
      completedSteps: _intOf(json['completed_steps'], 0),
      totalSteps: _intOf(json['total_steps'], 5),
      progressPct: _intOf(json['progress_pct'], 0),
      isComplete: _boolOf(json['is_complete']),
      nextStepKey: _stringOf(json['next_step_key']),
      steps: _mapListOf(
        json['steps'],
      ).map(ChecklistStep.fromJson).toList(growable: false),
    );
  }
}

class NightlySummaryFeedback {
  const NightlySummaryFeedback({
    required this.helpfulCount,
    required this.notHelpfulCount,
    required this.totalVotes,
    required this.helpfulPct,
    required this.lastVote,
    required this.lastVoteAtUtc,
  });

  final int helpfulCount;
  final int notHelpfulCount;
  final int totalVotes;
  final int helpfulPct;
  final String lastVote;
  final String lastVoteAtUtc;

  factory NightlySummaryFeedback.fromJson(Map<String, dynamic> json) {
    return NightlySummaryFeedback(
      helpfulCount: _intOf(json['helpful_count'], 0),
      notHelpfulCount: _intOf(json['not_helpful_count'], 0),
      totalVotes: _intOf(json['total_votes'], 0),
      helpfulPct: _intOf(json['helpful_pct'], 0),
      lastVote: _stringOf(json['last_vote']),
      lastVoteAtUtc: _stringOf(json['last_vote_at_utc']),
    );
  }
}

class AutomationFeedbackLoop {
  const AutomationFeedbackLoop({
    required this.helpfulCount,
    required this.notHelpfulCount,
    required this.totalVotes,
    required this.helpfulPct,
    required this.lastVote,
    required this.lastVoteAtUtc,
    required this.lastCommandId,
    required this.lastCommandAction,
    required this.statusLine,
  });

  final int helpfulCount;
  final int notHelpfulCount;
  final int totalVotes;
  final int helpfulPct;
  final String lastVote;
  final String lastVoteAtUtc;
  final String lastCommandId;
  final String lastCommandAction;
  final String statusLine;

  factory AutomationFeedbackLoop.fromJson(Map<String, dynamic> json) {
    return AutomationFeedbackLoop(
      helpfulCount: _intOf(json['helpful_count'], 0),
      notHelpfulCount: _intOf(json['not_helpful_count'], 0),
      totalVotes: _intOf(json['total_votes'], 0),
      helpfulPct: _intOf(json['helpful_pct'], 0),
      lastVote: _stringOf(json['last_vote']),
      lastVoteAtUtc: _stringOf(json['last_vote_at_utc']),
      lastCommandId: _stringOf(json['last_command_id']),
      lastCommandAction: _stringOf(json['last_command_action']),
      statusLine: _stringOf(
        json['status_line'],
        'No command feedback yet. Rate your latest automation to tune reliability.',
      ),
    );
  }
}

class BetaMetrics {
  const BetaMetrics({
    required this.windowDays,
    required this.activationProgressPct,
    required this.first3NightsCompleted,
    required this.first3NightsTotal,
    required this.commandTotal7d,
    required this.commandCompletionRatePct,
    required this.windDownSessions7d,
    required this.nightlyFeedbackTotal,
    required this.nightlyFeedbackHelpfulPct,
    required this.automationFeedbackTotal,
    required this.automationFeedbackHelpfulPct,
    required this.cohortStatusLine,
    required this.qualityGateLine,
    required this.generatedAtUtc,
  });

  final int windowDays;
  final int activationProgressPct;
  final int first3NightsCompleted;
  final int first3NightsTotal;
  final int commandTotal7d;
  final int commandCompletionRatePct;
  final int windDownSessions7d;
  final int nightlyFeedbackTotal;
  final int nightlyFeedbackHelpfulPct;
  final int automationFeedbackTotal;
  final int automationFeedbackHelpfulPct;
  final String cohortStatusLine;
  final String qualityGateLine;
  final String generatedAtUtc;

  factory BetaMetrics.fromJson(Map<String, dynamic> json) {
    return BetaMetrics(
      windowDays: _intOf(json['window_days'], 7),
      activationProgressPct: _intOf(json['activation_progress_pct'], 0),
      first3NightsCompleted: _intOf(json['first_3_nights_completed'], 0),
      first3NightsTotal: _intOf(json['first_3_nights_total'], 5),
      commandTotal7d: _intOf(json['command_total_7d'], 0),
      commandCompletionRatePct: _intOf(json['command_completion_rate_pct'], 0),
      windDownSessions7d: _intOf(json['wind_down_sessions_7d'], 0),
      nightlyFeedbackTotal: _intOf(json['nightly_feedback_total'], 0),
      nightlyFeedbackHelpfulPct: _intOf(
        json['nightly_feedback_helpful_pct'],
        0,
      ),
      automationFeedbackTotal: _intOf(json['automation_feedback_total'], 0),
      automationFeedbackHelpfulPct: _intOf(
        json['automation_feedback_helpful_pct'],
        0,
      ),
      cohortStatusLine: _stringOf(json['cohort_status_line']),
      qualityGateLine: _stringOf(json['quality_gate_line']),
      generatedAtUtc: _stringOf(json['generated_at_utc']),
    );
  }
}

class BedStateSnapshot {
  const BedStateSnapshot({
    required this.schemaVersion,
    required this.capabilities,
    required this.updatedAt,
    required this.stale,
    required this.deviceOnline,
    required this.source,
    required this.emotionState,
    required this.activePersonality,
    required this.biometricSummary,
    required this.deviceHealthStatus,
  });

  final String schemaVersion;
  final List<String> capabilities;
  final String updatedAt;
  final bool stale;
  final bool deviceOnline;
  final String source;
  final String emotionState;
  final String activePersonality;
  final Map<String, dynamic> biometricSummary;
  final Map<String, dynamic> deviceHealthStatus;

  factory BedStateSnapshot.fromJson(Map<String, dynamic> json) {
    final state = _mapOf(json['state']);
    return BedStateSnapshot(
      schemaVersion: _stringOf(json['schema_version'], '2.0'),
      capabilities: (json['capabilities'] is List)
          ? List<String>.from(
              (json['capabilities'] as List)
                  .map((item) => _stringOf(item))
                  .where((item) => item.isNotEmpty),
            )
          : const <String>[],
      updatedAt: _stringOf(json['updated_at']),
      stale: _boolOf(json['stale']),
      deviceOnline: _boolOf(json['device_online']),
      source: _stringOf(json['source'], 'unknown'),
      emotionState: _stringOf(state['emotion_state'], 'neutral'),
      activePersonality: _stringOf(state['active_personality'], 'guide'),
      biometricSummary: _mapOf(state['biometric_summary']),
      deviceHealthStatus: _mapOf(state['device_health_status']),
    );
  }
}

class TrialStatus {
  const TrialStatus({
    required this.subscriptionStatus,
    required this.trialActive,
    required this.trialDaysRemaining,
    required this.trialEndDate,
    required this.features,
  });

  final String subscriptionStatus;
  final bool trialActive;
  final int? trialDaysRemaining;
  final String trialEndDate;
  final Map<String, int> features;

  bool get isFree => subscriptionStatus == 'free';
  bool get isPremiumLike =>
      subscriptionStatus == 'trial' || subscriptionStatus == 'premium';

  factory TrialStatus.fromJson(Map<String, dynamic> json) {
    final rawFeatures = _mapOf(json['features']);
    return TrialStatus(
      subscriptionStatus: _stringOf(json['subscription_status'], 'free'),
      trialActive: _boolOf(json['trial_active']),
      trialDaysRemaining: json['trial_days_remaining'] == null
          ? null
          : _intOf(json['trial_days_remaining']),
      trialEndDate: _stringOf(json['trial_end_date']),
      features: rawFeatures.map((key, value) => MapEntry(key, _intOf(value))),
    );
  }
}

class SceneItem {
  const SceneItem({
    required this.sceneKey,
    required this.label,
    required this.summary,
    required this.previewSeconds,
  });

  final String sceneKey;
  final String label;
  final String summary;
  final double previewSeconds;

  factory SceneItem.fromJson(Map<String, dynamic> json) {
    return SceneItem(
      sceneKey: _stringOf(json['scene_key']),
      label: _stringOf(json['label'], 'Scene'),
      summary: _stringOf(json['summary']),
      previewSeconds: _doubleOf(json['preview_seconds'], 3),
    );
  }
}

class SceneGallery {
  const SceneGallery({
    required this.previewDurationSeconds,
    required this.items,
  });

  final double previewDurationSeconds;
  final List<SceneItem> items;

  factory SceneGallery.fromJson(Map<String, dynamic> json) {
    return SceneGallery(
      previewDurationSeconds: _doubleOf(json['preview_duration_seconds'], 3),
      items: _mapListOf(
        json['items'],
      ).map(SceneItem.fromJson).toList(growable: false),
    );
  }
}

class ScenePreviewResult {
  const ScenePreviewResult({
    required this.sceneKey,
    required this.sceneLabel,
    required this.previewDurationSeconds,
    required this.elapsedSeconds,
    required this.message,
    required this.traceId,
  });

  final String sceneKey;
  final String sceneLabel;
  final double previewDurationSeconds;
  final double elapsedSeconds;
  final String message;
  final String traceId;

  factory ScenePreviewResult.fromJson(Map<String, dynamic> json) {
    return ScenePreviewResult(
      sceneKey: _stringOf(json['scene_key']),
      sceneLabel: _stringOf(json['scene_label'], 'Scene'),
      previewDurationSeconds: _doubleOf(json['preview_duration_seconds'], 3),
      elapsedSeconds: _doubleOf(json['elapsed_seconds'], 0),
      message: _stringOf(json['message'], 'Preview complete.'),
      traceId: _stringOf(json['trace_id']),
    );
  }
}

class SceneSaveResult {
  const SceneSaveResult({
    required this.sceneKey,
    required this.sceneLabel,
    required this.message,
    required this.traceId,
  });

  final String sceneKey;
  final String sceneLabel;
  final String message;
  final String traceId;

  factory SceneSaveResult.fromJson(Map<String, dynamic> json) {
    return SceneSaveResult(
      sceneKey: _stringOf(json['scene_key']),
      sceneLabel: _stringOf(json['scene_label'], 'Scene'),
      message: _stringOf(json['message'], 'Scene saved for tonight.'),
      traceId: _stringOf(json['trace_id']),
    );
  }
}

class TimelineItem {
  const TimelineItem({
    required this.time,
    required this.event,
    required this.status,
    required this.commandId,
  });

  final String time;
  final String event;
  final String status;
  final String commandId;

  bool get isQuietHoursSignal {
    return status == 'quiet' ||
        status == 'override' ||
        event.toLowerCase().contains('quiet hours');
  }

  factory TimelineItem.fromJson(Map<String, dynamic> json) {
    return TimelineItem(
      time: _stringOf(json['time'], 'Now'),
      event: _stringOf(json['event'], 'Bed update'),
      status: _stringOf(json['status'], 'info'),
      commandId: _stringOf(json['command_id']),
    );
  }
}

class UserSettings {
  const UserSettings({
    required this.responseStyle,
    required this.engagementLevel,
    required this.partnerModeEnabled,
    required this.windDownMinutes,
    this.bedtimeDriftAutomationEnabled = true,
    this.quietHoursOverrideLimitMinutes = 120,
    this.weeklyInsightEnabled = true,
  });

  final String responseStyle;
  final String engagementLevel;
  final bool partnerModeEnabled;
  final int windDownMinutes;
  final bool bedtimeDriftAutomationEnabled;
  final int quietHoursOverrideLimitMinutes;
  final bool weeklyInsightEnabled;

  factory UserSettings.fromJson(Map<String, dynamic> json) {
    return UserSettings(
      responseStyle: _stringOf(json['response_style'], 'balanced'),
      engagementLevel: _stringOf(json['engagement_level'], 'high'),
      partnerModeEnabled: _boolOf(json['partner_mode_enabled']),
      windDownMinutes: _intOf(json['wind_down_minutes'], 45),
      bedtimeDriftAutomationEnabled: _boolOf(
        json['bedtime_drift_automation_enabled'],
        true,
      ),
      quietHoursOverrideLimitMinutes: _intOf(
        json['quiet_hours_override_limit_minutes'],
        120,
      ),
      weeklyInsightEnabled: _boolOf(json['weekly_insight_enabled'], true),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'response_style': responseStyle,
      'engagement_level': engagementLevel,
      'partner_mode_enabled': partnerModeEnabled,
      'wind_down_minutes': windDownMinutes,
      'bedtime_drift_automation_enabled': bedtimeDriftAutomationEnabled,
      'quiet_hours_override_limit_minutes': quietHoursOverrideLimitMinutes,
      'weekly_insight_enabled': weeklyInsightEnabled,
    };
  }
}

class UserProfilePrefs {
  const UserProfilePrefs({
    required this.displayName,
    required this.timezone,
    required this.pushEnabled,
    required this.emailEnabled,
  });

  final String displayName;
  final String timezone;
  final bool pushEnabled;
  final bool emailEnabled;

  factory UserProfilePrefs.fromJson(Map<String, dynamic> json) {
    return UserProfilePrefs(
      displayName: _stringOf(json['display_name'], 'User'),
      timezone: _stringOf(json['timezone'], 'Asia/Kuwait'),
      pushEnabled: _boolOf(json['push_enabled'], true),
      emailEnabled: _boolOf(json['email_enabled']),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'display_name': displayName,
      'timezone': timezone,
      'push_enabled': pushEnabled,
      'email_enabled': emailEnabled,
    };
  }
}

class DeviceCommandReceipt {
  const DeviceCommandReceipt({
    required this.action,
    required this.message,
    required this.commandId,
    required this.lastCommandResult,
    required this.timeline,
    required this.overrideUntilUtc,
  });

  final String action;
  final String message;
  final String commandId;
  final CommandResult? lastCommandResult;
  final List<TimelineItem> timeline;
  final String overrideUntilUtc;

  factory DeviceCommandReceipt.fromJson(Map<String, dynamic> json) {
    final rawResult = _mapOf(json['last_command_result']);
    return DeviceCommandReceipt(
      action: _stringOf(json['action']),
      message: _stringOf(json['message'], 'Command sent.'),
      commandId: _stringOf(json['command_id']),
      lastCommandResult: rawResult.isEmpty
          ? null
          : CommandResult.fromJson(rawResult),
      timeline: _mapListOf(
        json['timeline'],
      ).map(TimelineItem.fromJson).toList(growable: false),
      overrideUntilUtc: _stringOf(json['override_until_utc']),
    );
  }
}

class DashboardBundle {
  const DashboardBundle({required this.dashboard, required this.trialStatus});

  final DashboardSummary dashboard;
  final TrialStatus trialStatus;
}

class SettingsBundle {
  const SettingsBundle({required this.settings, required this.profile});

  final UserSettings settings;
  final UserProfilePrefs profile;
}
