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

  String get firstName {
    final trimmed = displayName.trim();
    if (trimmed.isEmpty) {
      return 'User';
    }
    return trimmed.split(RegExp(r'\s+')).first;
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

class OtpRequestResult {
  const OtpRequestResult({
    required this.requestId,
    required this.phoneNumberMasked,
    required this.expiresInSeconds,
    required this.expiresAt,
    required this.delivery,
    this.debugCode = '',
  });

  final String requestId;
  final String phoneNumberMasked;
  final int expiresInSeconds;
  final String expiresAt;
  final String delivery;
  final String debugCode;

  factory OtpRequestResult.fromJson(Map<String, dynamic> json) {
    return OtpRequestResult(
      requestId: _stringOf(json['request_id']),
      phoneNumberMasked: _stringOf(json['phone_number_masked']),
      expiresInSeconds: _intOf(json['expires_in'], 600),
      expiresAt: _stringOf(json['expires_at']),
      delivery: _stringOf(json['delivery'], 'simulated'),
      debugCode: _stringOf(json['debug_code']),
    );
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
    required this.feedbackTotalVotes,
    required this.feedbackHelpfulPct,
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
  final int feedbackTotalVotes;
  final int feedbackHelpfulPct;
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
      feedbackTotalVotes: _intOf(json['feedback_total_votes'], 0),
      feedbackHelpfulPct: _intOf(json['feedback_helpful_pct'], 0),
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
    this.premium = false,
  });

  final String sceneKey;
  final String label;
  final String summary;
  final double previewSeconds;
  final bool premium;

  factory SceneItem.fromJson(Map<String, dynamic> json) {
    return SceneItem(
      sceneKey: _stringOf(json['scene_key']),
      label: _stringOf(json['label'], 'Scene'),
      summary: _stringOf(json['summary']),
      previewSeconds: _doubleOf(json['preview_seconds'], 3),
      premium: _boolOf(json['premium']),
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
    this.premium = false,
  });

  final String sceneKey;
  final String sceneLabel;
  final String message;
  final String traceId;
  final bool premium;

  factory SceneSaveResult.fromJson(Map<String, dynamic> json) {
    return SceneSaveResult(
      sceneKey: _stringOf(json['scene_key']),
      sceneLabel: _stringOf(json['scene_label'], 'Scene'),
      message: _stringOf(json['message'], 'Scene saved for tonight.'),
      traceId: _stringOf(json['trace_id']),
      premium: _boolOf(json['premium']),
    );
  }
}

class UndoStatus {
  const UndoStatus({
    required this.canUndo,
    required this.actionType,
    required this.secondsRemaining,
  });

  final bool canUndo;
  final String actionType;
  final int? secondsRemaining;

  factory UndoStatus.fromJson(Map<String, dynamic> json) {
    return UndoStatus(
      canUndo: _boolOf(json['can_undo']),
      actionType: _stringOf(json['action_type']),
      secondsRemaining: json['seconds_remaining'] == null
          ? null
          : _intOf(json['seconds_remaining']),
    );
  }
}

class UndoResult {
  const UndoResult({
    required this.undone,
    required this.message,
  });

  final String undone;
  final String message;

  factory UndoResult.fromJson(Map<String, dynamic> json) {
    return UndoResult(
      undone: _stringOf(json['undone']),
      message: _stringOf(json['message'], 'Action undone successfully.'),
    );
  }
}

class TimelineItem {
  const TimelineItem({
    required this.time,
    required this.event,
    required this.status,
    required this.commandId,
    this.priority = 0,
  });

  final String time;
  final String event;
  final String status;
  final String commandId;
  final int priority;

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
      priority: _intOf(json['priority'], 0),
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
    this.locationMode = 'auto',
    this.countryCode = '',
    this.city = '',
    this.latitude,
    this.longitude,
    this.themeMode = 'system',
  });

  final String displayName;
  final String timezone;
  final bool pushEnabled;
  final bool emailEnabled;
  final String locationMode;
  final String countryCode;
  final String city;
  final double? latitude;
  final double? longitude;
  final String themeMode;

  UserProfilePrefs copyWith({
    String? displayName,
    String? timezone,
    bool? pushEnabled,
    bool? emailEnabled,
    String? locationMode,
    String? countryCode,
    String? city,
    double? latitude,
    double? longitude,
    String? themeMode,
    bool clearLatitude = false,
    bool clearLongitude = false,
  }) {
    return UserProfilePrefs(
      displayName: displayName ?? this.displayName,
      timezone: timezone ?? this.timezone,
      pushEnabled: pushEnabled ?? this.pushEnabled,
      emailEnabled: emailEnabled ?? this.emailEnabled,
      locationMode: locationMode ?? this.locationMode,
      countryCode: countryCode ?? this.countryCode,
      city: city ?? this.city,
      latitude: clearLatitude ? null : (latitude ?? this.latitude),
      longitude: clearLongitude ? null : (longitude ?? this.longitude),
      themeMode: themeMode ?? this.themeMode,
    );
  }

  String resolvedDisplayName(MobileUser user) {
    final candidate = displayName.trim();
    if (candidate.isNotEmpty) {
      return candidate;
    }
    return user.firstName;
  }

  factory UserProfilePrefs.fromJson(Map<String, dynamic> json) {
    return UserProfilePrefs(
      displayName: _stringOf(json['display_name'], 'User'),
      timezone: _stringOf(json['timezone'], 'Asia/Kuwait'),
      pushEnabled: _boolOf(json['push_enabled'], true),
      emailEnabled: _boolOf(json['email_enabled']),
      locationMode: _stringOf(json['location_mode'], 'auto'),
      countryCode: _stringOf(json['country_code']).toUpperCase(),
      city: _stringOf(json['city']),
      latitude: json['latitude'] == null ? null : _doubleOf(json['latitude']),
      longitude: json['longitude'] == null ? null : _doubleOf(json['longitude']),
      themeMode: _stringOf(json['theme_mode'], 'system'),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'display_name': displayName,
      'timezone': timezone,
      'push_enabled': pushEnabled,
      'email_enabled': emailEnabled,
      'location_mode': locationMode,
      'country_code': countryCode,
      'city': city,
      'latitude': latitude,
      'longitude': longitude,
      'theme_mode': themeMode,
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

class IslamicOverview {
  const IslamicOverview({
    required this.prayers,
    required this.nextPrayer,
    required this.location,
    required this.hadith,
    required this.sleepHadith,
    required this.hijri,
    required this.islamicEvent,
    required this.ramadanActive,
    required this.sunnahTip,
    required this.ledColor,
  });

  final Map<String, String> prayers;
  final PrayerCountdown nextPrayer;
  final PrayerLocation location;
  final Map<String, dynamic> hadith;
  final Map<String, dynamic> sleepHadith;
  final Map<String, dynamic> hijri;
  final String islamicEvent;
  final bool ramadanActive;
  final String sunnahTip;
  final String ledColor;

  factory IslamicOverview.fromJson(Map<String, dynamic> json) {
    final rawPrayers = _mapOf(json['prayers']);
    return IslamicOverview(
      prayers: rawPrayers.map(
        (key, value) => MapEntry(key.toString(), _stringOf(value)),
      ),
      nextPrayer: PrayerCountdown.fromJson(_mapOf(json['next_prayer'])),
      location: PrayerLocation.fromJson(_mapOf(json['location'])),
      hadith: _mapOf(json['hadith']),
      sleepHadith: _mapOf(json['sleep_hadith']),
      hijri: _mapOf(json['hijri']),
      islamicEvent: _stringOf(json['islamic_event']),
      ramadanActive: _boolOf(json['ramadan_active']),
      sunnahTip: _stringOf(json['sunnah_tip']),
      ledColor: _stringOf(json['led_color'], '#FFFFFF'),
    );
  }
}

class PrayerCountdown {
  const PrayerCountdown({
    required this.name,
    required this.time,
    required this.minutesUntil,
  });

  final String name;
  final String time;
  final int minutesUntil;

  factory PrayerCountdown.fromJson(Map<String, dynamic> json) {
    return PrayerCountdown(
      name: _stringOf(json['name'], 'Unknown'),
      time: _stringOf(json['time']),
      minutesUntil: _intOf(json['minutes_until'], -1),
    );
  }
}

class PrayerLocation {
  const PrayerLocation({
    required this.mode,
    required this.city,
    required this.countryCode,
    required this.countryName,
    required this.timezone,
    required this.latitude,
    required this.longitude,
    required this.label,
  });

  final String mode;
  final String city;
  final String countryCode;
  final String countryName;
  final String timezone;
  final double? latitude;
  final double? longitude;
  final String label;

  factory PrayerLocation.fromJson(Map<String, dynamic> json) {
    return PrayerLocation(
      mode: _stringOf(json['mode'], 'auto'),
      city: _stringOf(json['city']),
      countryCode: _stringOf(json['country_code']).toUpperCase(),
      countryName: _stringOf(json['country_name']),
      timezone: _stringOf(json['timezone']),
      latitude: json['latitude'] == null ? null : _doubleOf(json['latitude']),
      longitude: json['longitude'] == null ? null : _doubleOf(json['longitude']),
      label: _stringOf(json['label'], 'Location pending'),
    );
  }
}

class SubscriptionStatus {
  const SubscriptionStatus({
    required this.subscriptionStatus,
    required this.trialActive,
    required this.trialDaysRemaining,
    required this.trialEndDate,
    required this.planTier,
    required this.billingInterval,
    required this.paymentProvider,
    required this.priceKwd,
    required this.status,
    required this.nextRenewalAt,
    required this.graceEndAt,
    required this.providerSubscriptionId,
    required this.providerPlanId,
    required this.providerStatus,
    required this.startedAt,
    required this.lastPaymentAt,
    required this.cancelledAt,
  });

  final String subscriptionStatus;
  final bool trialActive;
  final int? trialDaysRemaining;
  final String trialEndDate;
  final String planTier;
  final String billingInterval;
  final String paymentProvider;
  final double priceKwd;
  final String status;
  final String nextRenewalAt;
  final String graceEndAt;
  final String providerSubscriptionId;
  final String providerPlanId;
  final String providerStatus;
  final String startedAt;
  final String lastPaymentAt;
  final String cancelledAt;

  bool get isPremiumLike =>
      subscriptionStatus == 'premium' || subscriptionStatus == 'trial';

  factory SubscriptionStatus.fromJson(Map<String, dynamic> json) {
    return SubscriptionStatus(
      subscriptionStatus: _stringOf(json['subscription_status'], 'free'),
      trialActive: _boolOf(json['trial_active']),
      trialDaysRemaining: json['trial_days_remaining'] == null
          ? null
          : _intOf(json['trial_days_remaining']),
      trialEndDate: _stringOf(json['trial_end_date']),
      planTier: _stringOf(json['plan_tier'], 'free'),
      billingInterval: _stringOf(json['billing_interval'], 'monthly'),
      paymentProvider: _stringOf(json['payment_provider'], 'none'),
      priceKwd: _doubleOf(json['price_kwd'], 0),
      status: _stringOf(json['status'], 'active'),
      nextRenewalAt: _stringOf(json['next_renewal_at']),
      graceEndAt: _stringOf(json['grace_end_at']),
      providerSubscriptionId: _stringOf(json['provider_subscription_id']),
      providerPlanId: _stringOf(json['provider_plan_id']),
      providerStatus: _stringOf(json['provider_status']),
      startedAt: _stringOf(json['started_at']),
      lastPaymentAt: _stringOf(json['last_payment_at']),
      cancelledAt: _stringOf(json['cancelled_at']),
    );
  }
}

class CheckoutSessionInfo {
  const CheckoutSessionInfo({
    required this.sessionId,
    required this.userId,
    required this.tier,
    required this.interval,
    required this.paymentProvider,
    required this.priceKwd,
    required this.status,
    required this.approveUrl,
    required this.providerSubscriptionId,
    required this.providerPlanId,
    required this.providerStatus,
  });

  final String sessionId;
  final String userId;
  final String tier;
  final String interval;
  final String paymentProvider;
  final double priceKwd;
  final String status;
  final String approveUrl;
  final String providerSubscriptionId;
  final String providerPlanId;
  final String providerStatus;

  factory CheckoutSessionInfo.fromJson(Map<String, dynamic> json) {
    return CheckoutSessionInfo(
      sessionId: _stringOf(json['session_id']),
      userId: _stringOf(json['user_id']),
      tier: _stringOf(json['tier'], 'standard'),
      interval: _stringOf(json['interval'], 'monthly'),
      paymentProvider: _stringOf(json['payment_provider'], 'paypal'),
      priceKwd: _doubleOf(json['price_kwd'], 0),
      status: _stringOf(json['status'], 'created'),
      approveUrl: _stringOf(json['approve_url']),
      providerSubscriptionId: _stringOf(json['provider_subscription_id']),
      providerPlanId: _stringOf(json['provider_plan_id']),
      providerStatus: _stringOf(json['provider_status']),
    );
  }
}

class BillingHistoryEvent {
  const BillingHistoryEvent({
    required this.eventId,
    required this.eventType,
    required this.summary,
    required this.status,
    required this.tier,
    required this.interval,
    required this.paymentProvider,
    required this.amountValue,
    required this.currency,
    required this.providerReference,
    required this.providerSubscriptionId,
    required this.providerPlanId,
    required this.createdAt,
  });

  final String eventId;
  final String eventType;
  final String summary;
  final String status;
  final String tier;
  final String interval;
  final String paymentProvider;
  final String amountValue;
  final String currency;
  final String providerReference;
  final String providerSubscriptionId;
  final String providerPlanId;
  final String createdAt;

  bool get isFailure =>
      eventType.toLowerCase().contains('failed') ||
      eventType.toLowerCase().contains('suspended');

  bool get isSuccess =>
      eventType.toLowerCase().contains('activated') ||
      eventType.toLowerCase().contains('renewed') ||
      eventType.toLowerCase().contains('completed');

  factory BillingHistoryEvent.fromJson(Map<String, dynamic> json) {
    return BillingHistoryEvent(
      eventId: _stringOf(json['event_id']),
      eventType: _stringOf(json['event_type']),
      summary: _stringOf(json['summary'], 'Billing event'),
      status: _stringOf(json['status']),
      tier: _stringOf(json['tier']),
      interval: _stringOf(json['interval'], 'monthly'),
      paymentProvider: _stringOf(json['payment_provider'], 'paypal'),
      amountValue: _stringOf(json['amount_value']),
      currency: _stringOf(json['currency']),
      providerReference: _stringOf(json['provider_reference']),
      providerSubscriptionId: _stringOf(json['provider_subscription_id']),
      providerPlanId: _stringOf(json['provider_plan_id']),
      createdAt: _stringOf(json['created_at']),
    );
  }
}

class BedPairingStatus {
  const BedPairingStatus({
    required this.paired,
    required this.deviceId,
    required this.bedLocation,
    required this.pairedAt,
    required this.provisioningVerified,
  });

  final bool paired;
  final String deviceId;
  final String bedLocation;
  final String pairedAt;
  final bool provisioningVerified;

  factory BedPairingStatus.fromJson(Map<String, dynamic> json) {
    return BedPairingStatus(
      paired: _boolOf(json['paired']),
      deviceId: _stringOf(json['device_id']),
      bedLocation: _stringOf(json['bed_location']),
      pairedAt: _stringOf(json['paired_at']),
      provisioningVerified: _boolOf(json['provisioning_verified']),
    );
  }
}

class AlarmSchedule {
  const AlarmSchedule({
    required this.alarmId,
    required this.time,
    required this.days,
    required this.enabled,
    required this.label,
    required this.sound,
    required this.vibrate,
    required this.createdAt,
    required this.updatedAt,
    required this.nextTriggerAtUtc,
  });

  final String alarmId;
  final String time;
  final List<int> days;
  final bool enabled;
  final String label;
  final String sound;
  final bool vibrate;
  final String createdAt;
  final String updatedAt;
  final String nextTriggerAtUtc;

  AlarmSchedule copyWith({
    String? alarmId,
    String? time,
    List<int>? days,
    bool? enabled,
    String? label,
    String? sound,
    bool? vibrate,
    String? createdAt,
    String? updatedAt,
    String? nextTriggerAtUtc,
  }) {
    return AlarmSchedule(
      alarmId: alarmId ?? this.alarmId,
      time: time ?? this.time,
      days: days ?? this.days,
      enabled: enabled ?? this.enabled,
      label: label ?? this.label,
      sound: sound ?? this.sound,
      vibrate: vibrate ?? this.vibrate,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      nextTriggerAtUtc: nextTriggerAtUtc ?? this.nextTriggerAtUtc,
    );
  }

  factory AlarmSchedule.fromJson(Map<String, dynamic> json) {
    final rawDays = json['days'] is List ? json['days'] as List : const <Object?>[];
    return AlarmSchedule(
      alarmId: _stringOf(json['alarm_id']),
      time: _stringOf(json['time'], '07:00'),
      days: rawDays.map((item) => _intOf(item)).where((day) => day >= 1 && day <= 7).toList(growable: false),
      enabled: _boolOf(json['enabled'], true),
      label: _stringOf(json['label']),
      sound: _stringOf(json['sound'], 'default'),
      vibrate: _boolOf(json['vibrate'], true),
      createdAt: _stringOf(json['created_at']),
      updatedAt: _stringOf(json['updated_at']),
      nextTriggerAtUtc: _stringOf(json['next_trigger_at_utc']),
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'alarm_id': alarmId,
      'time': time,
      'days': days,
      'enabled': enabled,
      'label': label,
      'sound': sound,
      'vibrate': vibrate,
    };
  }
}

class DeviceControls {
  const DeviceControls({
    required this.lightsOn,
    required this.audioOn,
    required this.alarmOn,
    required this.lightLevel,
  });

  final bool lightsOn;
  final bool audioOn;
  final bool alarmOn;
  final int lightLevel;

  DeviceControls copyWith({
    bool? lightsOn,
    bool? audioOn,
    bool? alarmOn,
    int? lightLevel,
  }) {
    return DeviceControls(
      lightsOn: lightsOn ?? this.lightsOn,
      audioOn: audioOn ?? this.audioOn,
      alarmOn: alarmOn ?? this.alarmOn,
      lightLevel: lightLevel ?? this.lightLevel,
    );
  }

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'lights_on': lightsOn,
      'audio_on': audioOn,
      'alarm_on': alarmOn,
      'light_level': lightLevel,
    };
  }

  factory DeviceControls.fromJson(Map<String, dynamic> json) {
    return DeviceControls(
      lightsOn: _boolOf(json['lights_on']),
      audioOn: _boolOf(json['audio_on']),
      alarmOn: _boolOf(json['alarm_on'], true),
      lightLevel: _intOf(json['light_level'], 65).clamp(0, 100),
    );
  }
}

class SpotifyConnectionStatus {
  const SpotifyConnectionStatus({
    required this.connected,
    required this.spotifyUserId,
    required this.spotifyEmail,
    required this.expiresAt,
    required this.scope,
  });

  final bool connected;
  final String spotifyUserId;
  final String spotifyEmail;
  final String expiresAt;
  final String scope;

  factory SpotifyConnectionStatus.fromJson(Map<String, dynamic> json) {
    return SpotifyConnectionStatus(
      connected: _boolOf(json['connected']),
      spotifyUserId: _stringOf(json['spotify_user_id']),
      spotifyEmail: _stringOf(json['spotify_email']),
      expiresAt: _stringOf(json['expires_at']),
      scope: _stringOf(json['scope']),
    );
  }
}

class SpotifyPlaybackStatus {
  const SpotifyPlaybackStatus({
    required this.connected,
    required this.isPlaying,
    required this.trackName,
    required this.artist,
    required this.deviceName,
  });

  final bool connected;
  final bool isPlaying;
  final String trackName;
  final String artist;
  final String deviceName;

  factory SpotifyPlaybackStatus.fromJson(Map<String, dynamic> json) {
    return SpotifyPlaybackStatus(
      connected: _boolOf(json['connected']),
      isPlaying: _boolOf(json['is_playing']),
      trackName: _stringOf(json['track_name']),
      artist: _stringOf(json['artist']),
      deviceName: _stringOf(json['device_name']),
    );
  }
}

class MobileDeviceInfo {
  const MobileDeviceInfo({
    required this.firmwareVersion,
    required this.deviceStatus,
    required this.userStripPin,
    required this.stateStripPin,
    required this.userStripLedCount,
    required this.stateStripLedCount,
    required this.pairedDeviceId,
    required this.pairedAt,
    required this.pairedBedLocation,
    required this.provisioningVerified,
    required this.alarmCount,
  });

  final String firmwareVersion;
  final String deviceStatus;
  final int userStripPin;
  final int stateStripPin;
  final int userStripLedCount;
  final int stateStripLedCount;
  final String pairedDeviceId;
  final String pairedAt;
  final String pairedBedLocation;
  final bool provisioningVerified;
  final int alarmCount;

  bool get online => deviceStatus.trim().toLowerCase() == 'online';

  factory MobileDeviceInfo.fromJson(Map<String, dynamic> json) {
    return MobileDeviceInfo(
      firmwareVersion: _stringOf(json['firmware_version'], '1.0.0'),
      deviceStatus: _stringOf(json['device_status'], 'offline'),
      userStripPin: _intOf(json['user_strip_pin'], 18),
      stateStripPin: _intOf(json['state_strip_pin'], 13),
      userStripLedCount: _intOf(json['user_strip_led_count'], 120),
      stateStripLedCount: _intOf(json['state_strip_led_count'], 60),
      pairedDeviceId: _stringOf(json['paired_device_id']),
      pairedAt: _stringOf(json['paired_at']),
      pairedBedLocation: _stringOf(json['paired_bed_location']),
      provisioningVerified: _boolOf(json['provisioning_verified']),
      alarmCount: _intOf(json['alarm_count'], 0),
    );
  }
}
