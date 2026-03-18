import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
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
  String? _pendingAction;

  Future<void> _refresh() async {
    ref.invalidate(dashboardBundleProvider);
    ref.invalidate(bedStateProvider);
    ref.invalidate(islamicOverviewProvider);
    ref.invalidate(subscriptionStatusProvider);
    await Future.wait<void>(<Future<void>>[
      ref.read(dashboardBundleProvider.future).then((_) {}),
      ref.read(bedStateProvider.future).then((_) {}),
      ref.read(islamicOverviewProvider.future).then((_) {}),
      ref.read(subscriptionStatusProvider.future).then((_) {}),
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
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(receipt.message)),
      );
      await _refresh();
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
    } finally {
      if (mounted) {
        setState(() {
          _pendingAction = null;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dashboardAsync = ref.watch(dashboardBundleProvider);
    final bedStateAsync = ref.watch(bedStateProvider);
    final islamicAsync = ref.watch(islamicOverviewProvider);
    final subscriptionAsync = ref.watch(subscriptionStatusProvider);

    final dashboard = dashboardAsync.valueOrNull;
    final bedState = bedStateAsync.valueOrNull;
    final islamic = islamicAsync.valueOrNull;
    final subscription = subscriptionAsync.valueOrNull;

    final error = dashboardAsync.error ??
        bedStateAsync.error ??
        islamicAsync.error ??
        subscriptionAsync.error;

    if (dashboard == null && error != null) {
      return _ErrorView(
        message: error is ApiException
            ? error.message
            : 'Unable to load Danah home.',
        onRetry: _refresh,
      );
    }

    if (dashboard == null ||
        bedState == null ||
        islamic == null ||
        subscription == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final greeting = _greetingForHour(DateTime.now().hour);
    final nextPrayer = islamic.nextPrayer;
    final progress = dashboard.dashboard.firstThreeNightsChecklist.progressPct;

    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
        children: <Widget>[
          Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 1120),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  PanelCard(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: <Color>[
                        SmartBedPalette.surface(theme.brightness),
                        SmartBedPalette.surfaceAlt(theme.brightness),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: <Widget>[
                                  Text(
                                    '$greeting, ${dashboard.dashboard.name}',
                                    style: theme.textTheme.headlineMedium,
                                  ),
                                  const SizedBox(height: 8),
                                  Text(
                                    'Dana is live. Your prayer timings, routines, and bed controls are synced for ${islamic.location.label}.',
                                    style: theme.textTheme.bodyLarge,
                                  ),
                                  const SizedBox(height: 16),
                                  Wrap(
                                    spacing: 10,
                                    runSpacing: 10,
                                    children: <Widget>[
                                      StatusPill(
                                        label: islamic.location.label,
                                        tone: StatusTone.info,
                                      ),
                                      StatusPill(
                                        label: bedState.deviceOnline
                                            ? (bedState.stale
                                                ? 'Bed online · stale'
                                                : 'Bed online')
                                            : 'Bed offline',
                                        tone: bedState.deviceOnline
                                            ? (bedState.stale
                                                ? StatusTone.warning
                                                : StatusTone.success)
                                            : StatusTone.danger,
                                      ),
                                      StatusPill(
                                        label: subscription.planTier.toUpperCase(),
                                        tone: subscription.isPremiumLike
                                            ? StatusTone.success
                                            : StatusTone.warning,
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                            IconButton(
                              onPressed: _refresh,
                              icon: const Icon(Icons.refresh_rounded),
                            ),
                          ],
                        ),
                        const SizedBox(height: 18),
                        Wrap(
                          spacing: 12,
                          runSpacing: 12,
                          children: _quickActions.map((action) {
                            final busy = _pendingAction == action.key;
                            return FilledButton.tonalIcon(
                              onPressed: action.route != null
                                  ? () => context.go(action.route!)
                                  : busy
                                      ? null
                                      : () => _runAction(action.key),
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
                          }).toList(growable: false),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final prayerCard = _NextPrayerCard(
                        nextPrayer: nextPrayer,
                        location: islamic.location.label,
                        ledColor: islamic.ledColor,
                      );
                      final summaryCard = _StatusSummaryCard(
                        weeklyInsight: dashboard.dashboard.weeklyInsight,
                        nightlySummary: dashboard.dashboard.nightlySummary,
                        bedState: bedState,
                        subscription: subscription,
                      );
                      if (constraints.maxWidth < 880) {
                        return Column(
                          children: <Widget>[
                            prayerCard,
                            const SizedBox(height: 18),
                            summaryCard,
                          ],
                        );
                      }
                      return Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Expanded(child: prayerCard),
                          const SizedBox(width: 18),
                          Expanded(child: summaryCard),
                        ],
                      );
                    },
                  ),
                  const SizedBox(height: 18),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final progressCard = _ProgressCard(
                        dashboard: dashboard.dashboard,
                        progress: progress,
                      );
                      final insightCard = _DanaInsightCard(
                        hadith: islamic.hadith,
                        tip: islamic.sunnahTip,
                        ramadanActive: islamic.ramadanActive,
                      );
                      if (constraints.maxWidth < 880) {
                        return Column(
                          children: <Widget>[
                            progressCard,
                            const SizedBox(height: 18),
                            insightCard,
                          ],
                        );
                      }
                      return Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Expanded(child: progressCard),
                          const SizedBox(width: 18),
                          Expanded(child: insightCard),
                        ],
                      );
                    },
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _NextPrayerCard extends StatelessWidget {
  const _NextPrayerCard({
    required this.nextPrayer,
    required this.location,
    required this.ledColor,
  });

  final PrayerCountdown nextPrayer;
  final String location;
  final String ledColor;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.mosque_rounded),
              const SizedBox(width: 10),
              Text('Next prayer', style: theme.textTheme.titleLarge),
            ],
          ),
          const SizedBox(height: 14),
          Text(nextPrayer.name, style: theme.textTheme.headlineMedium),
          const SizedBox(height: 6),
          Text(
            nextPrayer.minutesUntil >= 0
                ? 'In ${nextPrayer.minutesUntil} minutes · ${nextPrayer.time}'
                : 'Prayer timings are still syncing.',
            style: theme.textTheme.bodyLarge,
          ),
          const SizedBox(height: 10),
          Text(location, style: theme.textTheme.bodySmall),
          const SizedBox(height: 16),
          Row(
            children: <Widget>[
              Container(
                width: 16,
                height: 16,
                decoration: BoxDecoration(
                  color: _colorFromHex(ledColor),
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Dana will pause Spotify and shift the LED scene automatically.',
                  style: theme.textTheme.bodyMedium,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatusSummaryCard extends StatelessWidget {
  const _StatusSummaryCard({
    required this.weeklyInsight,
    required this.nightlySummary,
    required this.bedState,
    required this.subscription,
  });

  final WeeklyInsight weeklyInsight;
  final NightlySummary nightlySummary;
  final BedStateSnapshot bedState;
  final SubscriptionStatus subscription;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Tonight at a glance', style: theme.textTheme.titleLarge),
          const SizedBox(height: 14),
          Row(
            children: <Widget>[
              Expanded(
                child: _MetricTile(
                  label: 'Completion',
                  value: '${weeklyInsight.completionRatePct}%',
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _MetricTile(
                  label: 'Wind-downs',
                  value: '${weeklyInsight.windDownSessions}',
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: _MetricTile(
                  label: 'Plan',
                  value: subscription.planTier.toUpperCase(),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Text(nightlySummary.headline, style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(nightlySummary.focusLine, style: theme.textTheme.bodyMedium),
          const SizedBox(height: 10),
          StatusPill(
            label: bedState.activePersonality.toUpperCase(),
            tone: StatusTone.info,
          ),
        ],
      ),
    );
  }
}

class _ProgressCard extends StatelessWidget {
  const _ProgressCard({required this.dashboard, required this.progress});

  final DashboardSummary dashboard;
  final int progress;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Account momentum', style: theme.textTheme.titleLarge),
          const SizedBox(height: 12),
          LinearProgressIndicator(
            value: progress.clamp(0, 100) / 100,
            minHeight: 10,
            borderRadius: BorderRadius.circular(99),
          ),
          const SizedBox(height: 12),
          Text(
            '${dashboard.firstThreeNightsChecklist.completedSteps}/${dashboard.firstThreeNightsChecklist.totalSteps} onboarding milestones complete',
            style: theme.textTheme.bodyLarge,
          ),
          const SizedBox(height: 8),
          Text(
            dashboard.weeklyInsight.summary,
            style: theme.textTheme.bodyMedium,
          ),
        ],
      ),
    );
  }
}

class _DanaInsightCard extends StatelessWidget {
  const _DanaInsightCard({
    required this.hadith,
    required this.tip,
    required this.ramadanActive,
  });

  final Map<String, dynamic> hadith;
  final String tip;
  final bool ramadanActive;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(Icons.auto_awesome_rounded),
              const SizedBox(width: 10),
              Text('Dana insight', style: theme.textTheme.titleLarge),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            '${hadith['hadith'] ?? ''}',
            style: theme.textTheme.bodyLarge?.copyWith(
              fontStyle: FontStyle.italic,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '${hadith['source'] ?? ''}${ramadanActive ? ' · Ramadan mode active' : ''}',
            style: theme.textTheme.bodySmall,
          ),
          const SizedBox(height: 14),
          Text('Tonight\'s Sunnah tip', style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          Text(tip, style: theme.textTheme.bodyMedium),
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
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: SmartBedPalette.surfaceAlt(theme.brightness).withValues(
          alpha: 0.65,
        ),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(label, style: theme.textTheme.bodySmall),
          const SizedBox(height: 6),
          Text(
            value,
            style: theme.textTheme.titleLarge?.copyWith(
              color: SmartBedPalette.accent,
            ),
          ),
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
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
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
      ),
    );
  }
}

class _QuickAction {
  const _QuickAction({
    required this.key,
    required this.label,
    required this.icon,
    this.route,
  });

  final String key;
  final String label;
  final IconData icon;
  final String? route;
}

const _quickActions = <_QuickAction>[
  _QuickAction(
    key: 'winddown',
    label: 'Start wind-down',
    icon: Icons.nightlight_round,
  ),
  _QuickAction(
    key: 'controls',
    label: 'Bed controls',
    icon: Icons.tune_rounded,
    route: '/controls',
  ),
  _QuickAction(
    key: 'connect_bed',
    label: 'Connect bed',
    icon: Icons.qr_code_scanner_rounded,
    route: '/connect-bed',
  ),
  _QuickAction(
    key: 'spotify',
    label: 'Spotify',
    icon: Icons.music_note_rounded,
    route: '/spotify',
  ),
  _QuickAction(
    key: 'alarm',
    label: 'Alarm',
    icon: Icons.alarm_rounded,
    route: '/alarm',
  ),
  _QuickAction(
    key: 'optimize_room',
    label: 'Optimize room',
    icon: Icons.auto_fix_high_rounded,
  ),
  _QuickAction(
    key: 'bed_viewer',
    label: '3D bed view',
    icon: Icons.view_in_ar_rounded,
    route: '/bed-viewer',
  ),
  _QuickAction(
    key: 'scenes',
    label: 'Scenes',
    icon: Icons.palette_outlined,
    route: '/scenes',
  ),
  _QuickAction(
    key: 'timeline',
    label: 'Timeline',
    icon: Icons.timeline_rounded,
    route: '/timeline',
  ),
  _QuickAction(
    key: 'dana',
    label: 'Dana Live',
    icon: Icons.chat_bubble_outline_rounded,
    route: '/dana',
  ),
  _QuickAction(
    key: 'settings',
    label: 'Billing & settings',
    icon: Icons.credit_card_rounded,
    route: '/settings',
  ),
];

String _greetingForHour(int hour) {
  if (hour < 12) {
    return 'Good morning';
  }
  if (hour < 18) {
    return 'Good afternoon';
  }
  return 'Good evening';
}

Color _colorFromHex(String value) {
  final normalized = value.replaceAll('#', '').trim();
  if (normalized.length != 6) {
    return SmartBedPalette.accent;
  }
  return Color(int.parse('FF$normalized', radix: 16));
}
