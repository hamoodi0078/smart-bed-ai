import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../state/mobile_data.dart';
import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class ReportScreen extends ConsumerWidget {
  const ReportScreen({super.key});

  Future<void> _refresh(WidgetRef ref) async {
    ref.invalidate(dashboardBundleProvider);
    ref.invalidate(betaMetricsProvider);
    await Future.wait<void>(<Future<void>>[
      ref.read(dashboardBundleProvider.future).then((_) {}),
      ref.read(betaMetricsProvider.future).then((_) {}),
    ]);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dashboardAsync = ref.watch(dashboardBundleProvider);
    final betaAsync = ref.watch(betaMetricsProvider);

    final dashboard = dashboardAsync.valueOrNull;
    final metrics = betaAsync.valueOrNull;
    final error = dashboardAsync.error ?? betaAsync.error;

    if (dashboard == null && error != null) {
      return _ErrorView(
        message: error is ApiException
            ? error.message
            : 'Unable to load your report.',
        onRetry: () => _refresh(ref),
      );
    }

    if (dashboard == null || metrics == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final insight = dashboard.dashboard.weeklyInsight;
    final nightsCompleted = dashboard.dashboard.firstThreeNightsChecklist.completedSteps;

    return RefreshIndicator(
      onRefresh: () => _refresh(ref),
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
                        SmartBedPalette.surface(Theme.of(context).brightness),
                        SmartBedPalette.surfaceAlt(Theme.of(context).brightness),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text('Sleep report', style: Theme.of(context).textTheme.headlineMedium),
                        const SizedBox(height: 10),
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: <Widget>[
                            Text(
                              '${insight.completionRatePct}',
                              style: Theme.of(context).textTheme.displayMedium?.copyWith(
                                    color: SmartBedPalette.accent,
                                  ),
                            ),
                            const SizedBox(width: 6),
                            Padding(
                              padding: const EdgeInsets.only(bottom: 12),
                              child: Text('/ 100', style: Theme.of(context).textTheme.titleLarge),
                            ),
                          ],
                        ),
                        Text(insight.headline, style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 18),
                        Row(
                          children: <Widget>[
                            Expanded(
                              child: _StatCard(label: 'Avg sleep loop', value: '${metrics.windDownSessions7d} sessions'),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: _StatCard(label: 'Checklist', value: '$nightsCompleted/${dashboard.dashboard.firstThreeNightsChecklist.totalSteps}'),
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
                        Text('Weekly performance', style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 16),
                        _BarRow(
                          label: 'Wind-down consistency',
                          value: insight.windDownSessions,
                          max: 7,
                          highlight: SmartBedPalette.accent,
                        ),
                        _BarRow(
                          label: 'Automation completion',
                          value: insight.completionRatePct,
                          max: 100,
                          highlight: SmartBedPalette.secondaryAccent,
                        ),
                        _BarRow(
                          label: 'Helpful feedback',
                          value: metrics.nightlyFeedbackHelpfulPct,
                          max: 100,
                          highlight: SmartBedPalette.gold,
                        ),
                        _BarRow(
                          label: 'Command success',
                          value: metrics.commandCompletionRatePct,
                          max: 100,
                          highlight: SmartBedPalette.warmAccent,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final summaryCard = PanelCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text('Dana\'s summary', style: Theme.of(context).textTheme.titleLarge),
                            const SizedBox(height: 12),
                            Text(insight.summary, style: Theme.of(context).textTheme.bodyLarge),
                            const SizedBox(height: 12),
                            StatusPill(
                              label: metrics.activationProgressPct >= 70
                                  ? 'Momentum is strong'
                                  : 'Momentum needs work',
                              tone: metrics.activationProgressPct >= 70
                                  ? StatusTone.success
                                  : StatusTone.warning,
                            ),
                          ],
                        ),
                      );
                      final streakCard = PanelCard(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text('Recovery streak', style: Theme.of(context).textTheme.titleLarge),
                            const SizedBox(height: 12),
                            Text(
                              '${metrics.first3NightsCompleted} nights',
                              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                                    color: SmartBedPalette.warmAccent,
                                  ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              metrics.qualityGateLine,
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                          ],
                        ),
                      );
                      if (constraints.maxWidth < 880) {
                        return Column(
                          children: <Widget>[
                            summaryCard,
                            const SizedBox(height: 18),
                            streakCard,
                          ],
                        );
                      }
                      return Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Expanded(child: summaryCard),
                          const SizedBox(width: 18),
                          Expanded(child: streakCard),
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

class _BarRow extends StatelessWidget {
  const _BarRow({
    required this.label,
    required this.value,
    required this.max,
    required this.highlight,
  });

  final String label;
  final int value;
  final int max;
  final Color highlight;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final progress = max <= 0 ? 0.0 : (value / max).clamp(0, 1).toDouble();
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Expanded(child: Text(label, style: theme.textTheme.bodyLarge)),
              Text('$value', style: theme.textTheme.titleMedium),
            ],
          ),
          const SizedBox(height: 8),
          ClipRRect(
            borderRadius: BorderRadius.circular(99),
            child: LinearProgressIndicator(
              value: progress,
              minHeight: 12,
              backgroundColor: SmartBedPalette.surfaceAlt(theme.brightness),
              valueColor: AlwaysStoppedAnimation<Color>(highlight),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: SmartBedPalette.surfaceAlt(Theme.of(context).brightness).withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(label, style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 8),
          Text(
            value,
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
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
                const Icon(Icons.bar_chart_rounded, size: 36),
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
