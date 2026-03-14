import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../state/auth_controller.dart';
import '../../state/mobile_data.dart';
import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class DashboardScreen extends ConsumerStatefulWidget {
  const DashboardScreen({super.key});

  @override
  ConsumerState<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends ConsumerState<DashboardScreen> {
  Timer? _stateTimer;
  Timer? _timelineTimer;
  String? _pendingAction;
  bool _trialStarting = false;
  bool _feedbackSubmitting = false;
  bool _commandFeedbackSubmitting = false;

  @override
  void initState() {
    super.initState();
    _stateTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      ref.invalidate(bedStateProvider);
    });
    _timelineTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      ref.invalidate(timelineFeedProvider);
    });
  }

  @override
  void dispose() {
    _stateTimer?.cancel();
    _timelineTimer?.cancel();
    super.dispose();
  }

  Future<void> _refreshAll() async {
    ref.invalidate(bedStateProvider);
    ref.invalidate(dashboardBundleProvider);
    ref.invalidate(timelineFeedProvider);
    ref.invalidate(firstThreeNightsChecklistProvider);
    ref.invalidate(betaMetricsProvider);
    await Future.wait<void>(<Future<void>>[
      ref.read(bedStateProvider.future).then((_) {}),
      ref.read(dashboardBundleProvider.future).then((_) {}),
      ref.read(timelineFeedProvider.future).then((_) {}),
      ref.read(firstThreeNightsChecklistProvider.future).then((_) {}),
      ref.read(betaMetricsProvider.future).then((_) {}),
    ]);
  }

  Future<void> _runAction(String action) async {
    setState(() {
      _pendingAction = action;
    });

    try {
      final receipt = await ref
          .read(smartBedRepositoryProvider)
          .sendDeviceCommand(action);
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(receipt.message)));
      ref.invalidate(dashboardBundleProvider);
      ref.invalidate(timelineFeedProvider);
      ref.invalidate(bedStateProvider);
      ref.invalidate(firstThreeNightsChecklistProvider);
      ref.invalidate(betaMetricsProvider);
    } on ApiException catch (error) {
      _showMessage(error.message);
    } finally {
      if (mounted) {
        setState(() {
          _pendingAction = null;
        });
      }
    }
  }

  Future<void> _startTrial() async {
    setState(() {
      _trialStarting = true;
    });
    try {
      final status = await ref.read(smartBedRepositoryProvider).startTrial();
      if (!mounted) {
        return;
      }
      _showMessage(
        status.trialActive
            ? 'Your 7-day premium trial is active.'
            : 'Trial status updated.',
      );
      ref.invalidate(dashboardBundleProvider);
      ref.invalidate(betaMetricsProvider);
    } on ApiException catch (error) {
      _showMessage(error.message);
    } finally {
      if (mounted) {
        setState(() {
          _trialStarting = false;
        });
      }
    }
  }

  Future<void> _submitNightlyFeedback(
    String vote,
    String generatedAtUtc,
  ) async {
    setState(() {
      _feedbackSubmitting = true;
    });
    try {
      await ref
          .read(smartBedRepositoryProvider)
          .submitNightlySummaryFeedback(
            vote: vote,
            summaryGeneratedAtUtc: generatedAtUtc,
          );
      if (!mounted) {
        return;
      }
      _showMessage(
        vote == 'helpful'
            ? 'Thanks. Marked as helpful.'
            : 'Thanks. We will improve tomorrow\'s summary.',
      );
      ref.invalidate(dashboardBundleProvider);
      ref.invalidate(betaMetricsProvider);
    } on ApiException catch (error) {
      _showMessage(error.message);
    } finally {
      if (mounted) {
        setState(() {
          _feedbackSubmitting = false;
        });
      }
    }
  }

  Future<void> _submitCommandFeedback({
    required String commandId,
    required String vote,
  }) async {
    setState(() {
      _commandFeedbackSubmitting = true;
    });
    try {
      await ref.read(smartBedRepositoryProvider).submitCommandFeedback(
        commandId: commandId,
        vote: vote,
      );
      if (!mounted) {
        return;
      }
      _showMessage(
        vote == 'helpful'
            ? 'Command feedback saved. Nice signal for reliability.'
            : 'Command feedback saved. We will tune this automation.',
      );
      ref.invalidate(dashboardBundleProvider);
      ref.invalidate(betaMetricsProvider);
    } on ApiException catch (error) {
      _showMessage(error.message);
    } finally {
      if (mounted) {
        setState(() {
          _commandFeedbackSubmitting = false;
        });
      }
    }
  }

  void _showMessage(String message) {
    if (!mounted) {
      return;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final session = ref.watch(authControllerProvider).session;
    final dashboardAsync = ref.watch(dashboardBundleProvider);
    final bedStateAsync = ref.watch(bedStateProvider);
    final timelineAsync = ref.watch(timelineFeedProvider);
    final checklistAsync = ref.watch(firstThreeNightsChecklistProvider);
    final betaMetricsAsync = ref.watch(betaMetricsProvider);

    final dashboard = dashboardAsync.valueOrNull;
    final bedState = bedStateAsync.valueOrNull;
    final timeline = timelineAsync.valueOrNull ?? const <TimelineItem>[];
    final checklist = checklistAsync.valueOrNull;
    final betaMetrics = betaMetricsAsync.valueOrNull;

    final error = dashboardAsync.error ?? bedStateAsync.error;
    if ((dashboard == null || bedState == null) && error != null) {
      return _ErrorView(
        message: error is ApiException
            ? error.message
            : 'Unable to load the command center.',
        onRetry: _refreshAll,
      );
    }

    if (dashboard == null || bedState == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final quietHoursSignal = timeline.cast<TimelineItem?>().firstWhere(
      (item) => item?.isQuietHoursSignal ?? false,
      orElse: () => null,
    );
    final bedtimeDriftAlert = dashboard.dashboard.bedtimeDriftAlert.trim();
    final firstThreeNights =
        checklist ?? dashboard.dashboard.firstThreeNightsChecklist;

    return RefreshIndicator(
      onRefresh: _refreshAll,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
        children: <Widget>[
          PanelCard(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: <Color>[
                SmartBedPalette.surfaceDark,
                SmartBedPalette.surfaceLight,
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            'Command Center',
                            style: theme.textTheme.headlineMedium,
                          ),
                          const SizedBox(height: 6),
                          Text(
                            'Welcome back, ${session?.user.displayName ?? dashboard.dashboard.name}. Your bed state is live and the mobile surface is now the source of truth.',
                            style: theme.textTheme.bodyLarge,
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      onPressed: _refreshAll,
                      icon: const Icon(Icons.refresh_rounded),
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: <Widget>[
                    StatusPill(
                      label: bedState.deviceOnline
                          ? (bedState.stale ? 'Online, stale' : 'Online')
                          : 'Offline',
                      tone: _bedTone(bedState),
                    ),
                    StatusPill(
                      label: dashboard.trialStatus.subscriptionStatus
                          .toUpperCase(),
                      tone: dashboard.trialStatus.isPremiumLike
                          ? StatusTone.success
                          : StatusTone.warning,
                    ),
                    StatusPill(
                      label:
                          '${dashboard.dashboard.windDownMinutes} min wind-down',
                      tone: StatusTone.info,
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          PanelCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Live bed state', style: theme.textTheme.titleLarge),
                const SizedBox(height: 12),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: _MetricTile(
                        label: 'Emotion',
                        value: bedState.emotionState,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _MetricTile(
                        label: 'Personality',
                        value: bedState.activePersonality,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Text(
                  'Updated ${_friendlyTimestamp(bedState.updatedAt)} from ${bedState.source}.',
                  style: theme.textTheme.bodyMedium,
                ),
                if (bedState.capabilities.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: bedState.capabilities
                        .take(5)
                        .map(
                          (capability) => Chip(
                            label: Text(capability.replaceAll('_', ' ')),
                          ),
                        )
                        .toList(growable: false),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 18),
          PanelCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Quick actions', style: theme.textTheme.titleLarge),
                const SizedBox(height: 8),
                Text(
                  'These are the first habit-loop actions from the roadmap: wind-down, room optimization, wake recovery, reactive lights, and quiet-hours override.',
                  style: theme.textTheme.bodyMedium,
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: _quickActions
                      .map((action) {
                        final busy = _pendingAction == action.key;
                        return FilledButton.tonalIcon(
                          onPressed: busy ? null : () => _runAction(action.key),
                          icon: busy
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                  ),
                                )
                              : Icon(action.icon),
                          label: Text(action.label),
                        );
                      })
                      .toList(growable: false),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          _FirstThreeNightsCard(checklist: firstThreeNights),
          const SizedBox(height: 18),
          _WeeklyInsightCard(insight: dashboard.dashboard.weeklyInsight),
          const SizedBox(height: 18),
          _NightlySummaryCard(
            summary: dashboard.dashboard.nightlySummary,
            feedback: dashboard.dashboard.nightlySummaryFeedback,
            feedbackSubmitting: _feedbackSubmitting,
            onVote: (vote) => _submitNightlyFeedback(
              vote,
              dashboard.dashboard.nightlySummary.generatedAtUtc,
            ),
          ),
          const SizedBox(height: 18),
          if (betaMetrics != null)
            _BetaMetricsCard(metrics: betaMetrics)
          else if (betaMetricsAsync.isLoading)
            const PanelCard(
              child: Center(
                child: Padding(
                  padding: EdgeInsets.symmetric(vertical: 12),
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ),
          if (bedtimeDriftAlert.isNotEmpty) ...<Widget>[
            const SizedBox(height: 18),
            PanelCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[
                      Expanded(
                        child: Text(
                          'Bedtime drift alert',
                          style: theme.textTheme.titleLarge,
                        ),
                      ),
                      const StatusPill(
                        label: 'ATTENTION',
                        tone: StatusTone.warning,
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(bedtimeDriftAlert, style: theme.textTheme.bodyLarge),
                ],
              ),
            ),
          ],
          const SizedBox(height: 18),
          PanelCard(
            gradient: const LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: <Color>[
                SmartBedPalette.surfaceDark,
                SmartBedPalette.surfaceLight,
              ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Quiet hours signal', style: theme.textTheme.titleLarge),
                const SizedBox(height: 8),
                Text(
                  quietHoursSignal?.event ??
                      'Quiet hours are ready to protect the night. Trigger an override only when you really need it.',
                  style: theme.textTheme.bodyLarge,
                ),
                const SizedBox(height: 12),
                StatusPill(
                  label: quietHoursSignal?.status.toUpperCase() ?? 'READY',
                  tone: quietHoursSignal == null
                      ? StatusTone.info
                      : (quietHoursSignal.status == 'override'
                            ? StatusTone.warning
                            : StatusTone.neutral),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          _LastCommandCard(
            result: dashboard.dashboard.lastCommandResult,
            feedback: dashboard.dashboard.automationFeedbackLoop,
            onRetry: (action) => _runAction(action),
            feedbackSubmitting: _commandFeedbackSubmitting,
            onVote: (commandId, vote) => _submitCommandFeedback(
              commandId: commandId,
              vote: vote,
            ),
          ),
          const SizedBox(height: 18),
          if (dashboard.trialStatus.isFree)
            PanelCard(
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: <Color>[
                  SmartBedPalette.surfaceDark,
                  SmartBedPalette.accent,
                ],
              ),
              child: DefaultTextStyle(
                style: theme.textTheme.bodyMedium!.copyWith(
                  color: Colors.white.withValues(alpha: 0.86),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      'Unlock the 7-day premium trial',
                      style: theme.textTheme.titleLarge?.copyWith(
                        color: Colors.white,
                      ),
                    ),
                    const SizedBox(height: 10),
                    const Text(
                      'Use the roadmap revenue hook now: premium scenes, longer wind-down coverage, and more automation headroom.',
                    ),
                    const SizedBox(height: 14),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: <Widget>[
                        Chip(
                          label: Text(
                            '${dashboard.trialStatus.features['max_scenes'] ?? 3} scene slots',
                          ),
                        ),
                        Chip(
                          label: Text(
                            '${dashboard.trialStatus.features['wind_down_minutes'] ?? 10} min automations',
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 18),
                    FilledButton(
                      onPressed: _trialStarting ? null : _startTrial,
                      style: FilledButton.styleFrom(
                        backgroundColor: SmartBedPalette.secondaryAccent,
                        foregroundColor: SmartBedPalette.surfaceDark,
                      ),
                      child: _trialStarting
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Start 7-day trial'),
                    ),
                  ],
                ),
              ),
            )
          else
            PanelCard(
              child: Row(
                children: <Widget>[
                  const Icon(Icons.workspace_premium_rounded, size: 30),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      dashboard.trialStatus.trialActive
                          ? 'Trial active with ${dashboard.trialStatus.trialDaysRemaining ?? 0} day(s) remaining.'
                          : 'Premium access is active for this account.',
                      style: theme.textTheme.bodyLarge,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(22),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(label, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 6),
          Text(value.replaceAll('_', ' '), style: theme.textTheme.titleMedium),
        ],
      ),
    );
  }
}

class _WeeklyInsightCard extends StatelessWidget {
  const _WeeklyInsightCard({required this.insight});

  final WeeklyInsight insight;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final trendLabel = switch (insight.trend.toLowerCase()) {
      'up' => 'Trending up',
      'attention' => 'Needs attention',
      _ => 'Steady',
    };
    final trendTone = switch (insight.trend.toLowerCase()) {
      'up' => StatusTone.success,
      'attention' => StatusTone.warning,
      _ => StatusTone.info,
    };

    return PanelCard(
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: <Color>[
          SmartBedPalette.surfaceDark,
          SmartBedPalette.surfaceLight,
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  'Weekly insight',
                  style: theme.textTheme.titleLarge,
                ),
              ),
              StatusPill(label: trendLabel, tone: trendTone),
            ],
          ),
          const SizedBox(height: 10),
          Text(insight.headline, style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          Text(insight.summary, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: <Widget>[
              StatusPill(
                label: '${insight.windDownSessions} wind-down',
                tone: insight.windDownSessions > 0
                    ? StatusTone.success
                    : StatusTone.neutral,
              ),
              StatusPill(
                label: '${insight.completionRatePct}% completion',
                tone: insight.completionRatePct >= 80
                    ? StatusTone.success
                    : (insight.completionRatePct >= 40
                          ? StatusTone.info
                          : StatusTone.warning),
              ),
              StatusPill(
                label: '${insight.quietOverrides} override(s)',
                tone: insight.quietOverrides > 0
                    ? StatusTone.warning
                    : StatusTone.neutral,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _FirstThreeNightsCard extends StatelessWidget {
  const _FirstThreeNightsCard({required this.checklist});

  final FirstThreeNightsChecklist checklist;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final tone = checklist.isComplete ? StatusTone.success : StatusTone.info;
    return PanelCard(
      gradient: const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: <Color>[
          SmartBedPalette.surfaceDark,
          SmartBedPalette.surfaceLight,
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(checklist.title, style: theme.textTheme.titleLarge),
              ),
              StatusPill(
                label:
                    '${checklist.completedSteps}/${checklist.totalSteps} complete',
                tone: tone,
              ),
            ],
          ),
          const SizedBox(height: 10),
          LinearProgressIndicator(
            value: checklist.progressPct.clamp(0, 100) / 100.0,
            minHeight: 8,
            borderRadius: BorderRadius.circular(99),
          ),
          const SizedBox(height: 12),
          Text(
            checklist.isComplete
                ? 'First 3 Nights milestone is complete for this account.'
                : 'Next step: ${_friendlyStepLabel(checklist.nextStepKey)}',
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: 12),
          ...checklist.steps.map((step) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(
                    step.completed
                        ? Icons.check_circle_rounded
                        : Icons.radio_button_unchecked_rounded,
                    size: 20,
                    color: step.completed
                        ? SmartBedPalette.connected
                        : Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(step.label, style: theme.textTheme.titleSmall),
                        if (step.description.trim().isNotEmpty)
                          Text(
                            step.description,
                            style: theme.textTheme.bodySmall,
                          ),
                      ],
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }
}

class _NightlySummaryCard extends StatelessWidget {
  const _NightlySummaryCard({
    required this.summary,
    required this.feedback,
    required this.feedbackSubmitting,
    required this.onVote,
  });

  final NightlySummary summary;
  final NightlySummaryFeedback feedback;
  final bool feedbackSubmitting;
  final ValueChanged<String> onVote;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(summary.headline, style: theme.textTheme.titleLarge),
          const SizedBox(height: 6),
          StatusPill(label: summary.trendTitle, tone: StatusTone.info),
          const SizedBox(height: 12),
          Text(summary.focusLine, style: theme.textTheme.bodyLarge),
          const SizedBox(height: 10),
          Text(summary.sleepQualityLine, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 6),
          Text(summary.consistencyLine, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 6),
          Text(summary.recoveryPlanLine, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 14),
          Text(
            'Was this nightly summary helpful?',
            style: theme.textTheme.titleSmall,
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: <Widget>[
              FilledButton.tonalIcon(
                onPressed: feedbackSubmitting ? null : () => onVote('helpful'),
                icon: const Icon(Icons.thumb_up_alt_outlined),
                label: const Text('Helpful'),
              ),
              FilledButton.tonalIcon(
                onPressed: feedbackSubmitting
                    ? null
                    : () => onVote('not_helpful'),
                icon: const Icon(Icons.thumb_down_alt_outlined),
                label: const Text('Not helpful'),
              ),
              StatusPill(
                label:
                    '${feedback.helpfulPct}% helpful (${feedback.totalVotes} vote(s))',
                tone: feedback.totalVotes > 0
                    ? StatusTone.info
                    : StatusTone.neutral,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _BetaMetricsCard extends StatelessWidget {
  const _BetaMetricsCard({required this.metrics});

  final BetaMetrics metrics;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text('Beta metrics', style: theme.textTheme.titleLarge),
              ),
              StatusPill(
                label: '${metrics.activationProgressPct}% activated',
                tone: metrics.activationProgressPct >= 70
                    ? StatusTone.success
                    : StatusTone.warning,
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(metrics.cohortStatusLine, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 6),
          Text(metrics.qualityGateLine, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: <Widget>[
              StatusPill(
                label:
                    '${metrics.first3NightsCompleted}/${metrics.first3NightsTotal} checklist',
                tone: metrics.first3NightsCompleted >= metrics.first3NightsTotal
                    ? StatusTone.success
                    : StatusTone.info,
              ),
              StatusPill(
                label: '${metrics.commandCompletionRatePct}% command success',
                tone: metrics.commandCompletionRatePct >= 80
                    ? StatusTone.success
                    : StatusTone.warning,
              ),
              StatusPill(
                label: '${metrics.windDownSessions7d} wind-down (7d)',
                tone: metrics.windDownSessions7d > 0
                    ? StatusTone.success
                    : StatusTone.neutral,
              ),
              StatusPill(
                label: '${metrics.nightlyFeedbackHelpfulPct}% helpful feedback',
                tone: metrics.nightlyFeedbackTotal > 0
                    ? StatusTone.info
                    : StatusTone.neutral,
              ),
              StatusPill(
                label:
                    '${metrics.automationFeedbackHelpfulPct}% command feedback',
                tone: metrics.automationFeedbackTotal > 0
                    ? StatusTone.info
                    : StatusTone.neutral,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _LastCommandCard extends StatelessWidget {
  const _LastCommandCard({
    required this.result,
    required this.feedback,
    required this.onRetry,
    required this.feedbackSubmitting,
    required this.onVote,
  });

  final CommandResult? result;
  final AutomationFeedbackLoop feedback;
  final ValueChanged<String> onRetry;
  final bool feedbackSubmitting;
  final void Function(String commandId, String vote) onVote;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (result == null) {
      return PanelCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Text('Last command result', style: theme.textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(
              'No mobile command has been fired yet. Start with wind-down or room optimization to seed the timeline.',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 10),
            Text(feedback.statusLine, style: theme.textTheme.bodySmall),
          ],
        ),
      );
    }

    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  'Last command result',
                  style: theme.textTheme.titleLarge,
                ),
              ),
              StatusPill(
                label: result!.status.toUpperCase(),
                tone: result!.success ? StatusTone.success : StatusTone.warning,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(result!.summary, style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          Text(result!.diagnostic, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 12),
          Text(
            'Action: ${result!.action.replaceAll('_', ' ')}',
            style: theme.textTheme.bodyMedium,
          ),
          Text(
            'Seen ${_friendlyTimestamp(result!.timestampUtc)}',
            style: theme.textTheme.bodyMedium,
          ),
          if (result!.hasTrace) ...<Widget>[
            const SizedBox(height: 4),
            Text('Trace ${result!.traceId}', style: theme.textTheme.bodySmall),
          ],
          if (result!.retryAction.isNotEmpty) ...<Widget>[
            const SizedBox(height: 14),
            OutlinedButton.icon(
              onPressed: () => onRetry(result!.retryAction),
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('Retry action'),
            ),
          ],
          if (result!.commandId.isNotEmpty) ...<Widget>[
            const SizedBox(height: 14),
            Text(
              'Was this automation result helpful?',
              style: theme.textTheme.titleSmall,
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: <Widget>[
                FilledButton.tonalIcon(
                  onPressed: feedbackSubmitting
                      ? null
                      : () => onVote(result!.commandId, 'helpful'),
                  icon: const Icon(Icons.thumb_up_alt_outlined),
                  label: const Text('Helpful'),
                ),
                FilledButton.tonalIcon(
                  onPressed: feedbackSubmitting
                      ? null
                      : () => onVote(result!.commandId, 'not_helpful'),
                  icon: const Icon(Icons.thumb_down_alt_outlined),
                  label: const Text('Not helpful'),
                ),
                StatusPill(
                  label:
                      '${feedback.helpfulPct}% helpful (${feedback.totalVotes} vote(s))',
                  tone: feedback.totalVotes > 0
                      ? StatusTone.info
                      : StatusTone.neutral,
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(feedback.statusLine, style: theme.textTheme.bodySmall),
          ],
        ],
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});

  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: PanelCard(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              const Icon(Icons.wifi_off_rounded, size: 36),
              const SizedBox(height: 12),
              Text(message, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              FilledButton(onPressed: onRetry, child: const Text('Retry')),
            ],
          ),
        ),
      ),
    );
  }
}

StatusTone _bedTone(BedStateSnapshot state) {
  if (!state.deviceOnline) {
    return StatusTone.danger;
  }
  if (state.stale) {
    return StatusTone.warning;
  }
  return StatusTone.success;
}

String _friendlyStepLabel(String key) {
  return switch (key) {
    'signup' => 'Create mobile access',
    'first_scene_preview' => 'Preview first scene',
    'first_automation' => 'Trigger first automation',
    'first_winddown' => 'Start wind-down',
    'timeline_review' => 'Review timeline',
    _ => key.isEmpty ? 'Continue setup' : key.replaceAll('_', ' '),
  };
}

String _friendlyTimestamp(String raw) {
  final parsed = DateTime.tryParse(raw)?.toLocal();
  if (parsed == null) {
    return raw;
  }
  final hour = parsed.hour % 12 == 0 ? 12 : parsed.hour % 12;
  final minute = parsed.minute.toString().padLeft(2, '0');
  final suffix = parsed.hour >= 12 ? 'PM' : 'AM';
  return '$hour:$minute $suffix';
}

class _QuickAction {
  const _QuickAction({
    required this.key,
    required this.label,
    required this.icon,
  });

  final String key;
  final String label;
  final IconData icon;
}

const _quickActions = <_QuickAction>[
  _QuickAction(
    key: 'winddown',
    label: 'Wind-down',
    icon: Icons.nightlight_round,
  ),
  _QuickAction(
    key: 'optimize_room',
    label: 'Optimize room',
    icon: Icons.air_rounded,
  ),
  _QuickAction(
    key: 'wake_recovery',
    label: 'Wake recovery',
    icon: Icons.self_improvement_rounded,
  ),
  _QuickAction(
    key: 'reactive_lights',
    label: 'Reactive lights',
    icon: Icons.light_mode_rounded,
  ),
  _QuickAction(
    key: 'quiet_hours_override',
    label: 'Quiet override',
    icon: Icons.volume_off_rounded,
  ),
];
