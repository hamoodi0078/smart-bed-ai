import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../state/mobile_data.dart';
import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class TimelineScreen extends ConsumerStatefulWidget {
  const TimelineScreen({super.key});

  @override
  ConsumerState<TimelineScreen> createState() => _TimelineScreenState();
}

class _TimelineScreenState extends ConsumerState<TimelineScreen> {
  static const int _pollBackoffWindowTicks = 2;

  Timer? _pollTimer;
  bool _timelineReviewMarked = false;
  int _pollBackoffTicks = 0;

  @override
  void initState() {
    super.initState();
    Future<void>.microtask(_markTimelineReviewStep);
    _pollTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      _pollTimeline();
    });
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _refresh() async {
    _pollBackoffTicks = 0;
    ref.invalidate(timelineFeedProvider);
    try {
      await ref.read(timelineFeedProvider.future);
    } catch (_) {}
  }

  void _pollTimeline() {
    if (!mounted) {
      return;
    }
    if (_pollBackoffTicks > 0) {
      _pollBackoffTicks -= 1;
      return;
    }
    final current = ref.read(timelineFeedProvider);
    if (current.hasError && current.valueOrNull == null) {
      _pollBackoffTicks = _pollBackoffWindowTicks;
      return;
    }
    ref.invalidate(timelineFeedProvider);
  }

  Future<void> _markTimelineReviewStep() async {
    if (_timelineReviewMarked) {
      return;
    }
    _timelineReviewMarked = true;
    try {
      await ref
          .read(smartBedRepositoryProvider)
          .completeFirstThreeNightsStep('timeline_review');
      ref.invalidate(firstThreeNightsChecklistProvider);
      ref.invalidate(dashboardBundleProvider);
      ref.invalidate(betaMetricsProvider);
    } on ApiException {
      _timelineReviewMarked = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final timelineAsync = ref.watch(timelineFeedProvider);
    final items = timelineAsync.valueOrNull;
    final error = timelineAsync.error;

    if (items == null && error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: PanelCard(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Icon(Icons.timeline_rounded, size: 36),
                const SizedBox(height: 12),
                Text(
                  error is ApiException
                      ? error.message
                      : 'Unable to load your timeline.',
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                FilledButton(onPressed: _refresh, child: const Text('Retry')),
              ],
            ),
          ),
        ),
      );
    }

    if (items == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final queuedCount = items.where((item) => item.status == 'queued').length;
    final overrideCount = items
        .where((item) => item.status == 'override')
        .length;
    final windDownCount = items
        .where((item) => item.event.toLowerCase().contains('wind-down'))
        .length;
    final sortedItems = [...items]
      ..sort((a, b) => b.priority.compareTo(a.priority));
    final priorityNow = sortedItems
        .where((item) => item.priority >= 75)
        .take(2)
        .toList(growable: false);

    return RefreshIndicator(
      onRefresh: _refresh,
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
                Text('Timeline', style: theme.textTheme.headlineMedium),
                const SizedBox(height: 8),
                Text(
                  'This is the habit loop view for the first 45 days: what happened, what is cooling down, and whether wind-down is becoming a nightly pattern.',
                  style: theme.textTheme.bodyLarge,
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          PanelCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Pattern insight', style: theme.textTheme.titleLarge),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: <Widget>[
                    StatusPill(
                      label: '$windDownCount wind-down event(s)',
                      tone: windDownCount > 0
                          ? StatusTone.success
                          : StatusTone.neutral,
                    ),
                    StatusPill(
                      label: '$queuedCount queued action(s)',
                      tone: queuedCount > 0
                          ? StatusTone.warning
                          : StatusTone.info,
                    ),
                    StatusPill(
                      label: '$overrideCount override(s)',
                      tone: overrideCount > 0
                          ? StatusTone.warning
                          : StatusTone.neutral,
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Text(
                  windDownCount > 0
                      ? 'Wind-down has already shown up in the loop. Keep the bedtime sequence repeatable and the next-day review gets easier.'
                      : 'No wind-down event yet. Start with one command tonight so tomorrow has a real loop to review.',
                  style: theme.textTheme.bodyLarge,
                ),
              ],
            ),
          ),
          if (priorityNow.isNotEmpty) ...<Widget>[
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
                  Text('Priority now', style: theme.textTheme.titleLarge),
                  const SizedBox(height: 8),
                  ...priorityNow.map((item) {
                    return Padding(
                      padding: const EdgeInsets.only(bottom: 8),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          StatusPill(
                            label: 'P${item.priority}',
                            tone: _timelineTone(item.status),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              item.event,
                              style: theme.textTheme.bodyLarge,
                            ),
                          ),
                        ],
                      ),
                    );
                  }),
                ],
              ),
            ),
          ],
          const SizedBox(height: 18),
          ...sortedItems.map((item) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: PanelCard(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Container(
                      width: 52,
                      height: 52,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.surfaceContainer,
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: Text(
                        item.time,
                        textAlign: TextAlign.center,
                        style: theme.textTheme.labelLarge?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(item.event, style: theme.textTheme.titleMedium),
                          const SizedBox(height: 8),
                          Wrap(
                            spacing: 8,
                            runSpacing: 8,
                            children: <Widget>[
                              StatusPill(
                                label: item.status.toUpperCase(),
                                tone: _timelineTone(item.status),
                              ),
                              if (item.commandId.isNotEmpty)
                                StatusPill(
                                  label: item.commandId,
                                  tone: StatusTone.info,
                                ),
                              if (item.priority > 0)
                                StatusPill(
                                  label: 'P${item.priority}',
                                  tone: StatusTone.neutral,
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
        ],
      ),
    );
  }
}

StatusTone _timelineTone(String status) {
  switch (status) {
    case 'completed':
    case 'ready':
    case 'active':
      return StatusTone.success;
    case 'override':
    case 'review':
    case 'queued':
      return StatusTone.warning;
    case 'quiet':
      return StatusTone.info;
    default:
      return StatusTone.neutral;
  }
}
