import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../state/mobile_data.dart';
import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class ScenesScreen extends ConsumerStatefulWidget {
  const ScenesScreen({super.key});

  @override
  ConsumerState<ScenesScreen> createState() => _ScenesScreenState();
}

class _ScenesScreenState extends ConsumerState<ScenesScreen> {
  String? _busyKey;

  Future<void> _refresh() async {
    ref.invalidate(sceneGalleryProvider);
    ref.invalidate(dashboardBundleProvider);
    await Future.wait<void>(<Future<void>>[
      ref
          .read(sceneGalleryProvider.future)
          .then((_) {})
          .catchError((_) => null),
      ref
          .read(dashboardBundleProvider.future)
          .then((_) {})
          .catchError((_) => null),
    ]);
  }

  Future<void> _previewScene(SceneItem item) async {
    setState(() {
      _busyKey = 'preview:${item.sceneKey}';
    });
    try {
      final result = await ref
          .read(smartBedRepositoryProvider)
          .previewScene(item.sceneKey);
      _showMessage('${result.sceneLabel}: ${result.message}');
    } on ApiException catch (error) {
      _showMessage(error.message);
    } finally {
      if (mounted) {
        setState(() {
          _busyKey = null;
        });
      }
    }
  }

  Future<void> _saveScene(SceneItem item) async {
    setState(() {
      _busyKey = 'save:${item.sceneKey}';
    });
    try {
      final result = await ref
          .read(smartBedRepositoryProvider)
          .saveSceneForTonight(item.sceneKey);
      _showMessage('${result.sceneLabel}: ${result.message}');
      ref.invalidate(bedStateProvider);
      ref.invalidate(timelineFeedProvider);
    } on ApiException catch (error) {
      _showMessage(error.message);
    } finally {
      if (mounted) {
        setState(() {
          _busyKey = null;
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
    final scenesAsync = ref.watch(sceneGalleryProvider);
    final dashboardAsync = ref.watch(dashboardBundleProvider);
    final scenes = scenesAsync.valueOrNull;
    final dashboard = dashboardAsync.valueOrNull;
    final error = scenesAsync.error ?? dashboardAsync.error;

    if (scenes == null && error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: PanelCard(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Icon(Icons.auto_awesome_outlined, size: 34),
                const SizedBox(height: 12),
                Text(
                  error is ApiException
                      ? error.message
                      : 'Unable to load scenes.',
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

    if (scenes == null) {
      return const Center(child: CircularProgressIndicator());
    }

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
                Text('Scene gallery', style: theme.textTheme.headlineMedium),
                const SizedBox(height: 8),
                Text(
                  'Preview a scene first, then save it for tonight. Dana keeps the lighting and wind-down transition aligned with your current plan.',
                  style: theme.textTheme.bodyLarge,
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: <Widget>[
                    StatusPill(
                      label:
                          '${scenes.previewDurationSeconds.toStringAsFixed(0)}s preview',
                      tone: StatusTone.info,
                    ),
                    if (dashboard != null)
                      StatusPill(
                        label: dashboard.trialStatus.subscriptionStatus
                            .toUpperCase(),
                        tone: dashboard.trialStatus.isPremiumLike
                            ? StatusTone.success
                            : StatusTone.warning,
                      ),
                    FilledButton.tonalIcon(
                      onPressed: () => context.go('/bed-viewer'),
                      icon: const Icon(Icons.view_in_ar_rounded),
                      label: const Text('Open 3D viewer'),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          if (dashboard != null && dashboard.trialStatus.isFree)
            PanelCard(
              child: Row(
                children: <Widget>[
                  const Icon(Icons.workspace_premium_outlined),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Premium scenes unlock after you upgrade your plan in Settings.',
                      style: theme.textTheme.bodyLarge,
                    ),
                  ),
                ],
              ),
            ),
          if (dashboard != null && dashboard.trialStatus.isFree)
            const SizedBox(height: 18),
          ...scenes.items.map((item) {
            final previewBusy = _busyKey == 'preview:${item.sceneKey}';
            final saveBusy = _busyKey == 'save:${item.sceneKey}';
            final lockedPremium = item.premium && (dashboard?.trialStatus.isFree ?? true);
            return Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: PanelCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Row(
                      children: <Widget>[
                        Expanded(
                          child: Text(
                            item.label,
                            style: theme.textTheme.titleLarge,
                          ),
                        ),
                        StatusPill(
                          label:
                              '${item.previewSeconds.toStringAsFixed(0)} sec',
                          tone: StatusTone.neutral,
                        ),
                        if (item.premium) ...<Widget>[
                          const SizedBox(width: 8),
                          const StatusPill(
                            label: 'PREMIUM',
                            tone: StatusTone.warning,
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(item.summary, style: theme.textTheme.bodyLarge),
                    if (lockedPremium) ...<Widget>[
                      const SizedBox(height: 8),
                      Text(
                        'Upgrade your plan in Settings to save this premium scene tonight.',
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                    const SizedBox(height: 16),
                    Row(
                      children: <Widget>[
                        Expanded(
                          child: FilledButton.tonalIcon(
                            onPressed: previewBusy
                                ? null
                                : () => _previewScene(item),
                            icon: previewBusy
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Icon(Icons.play_circle_outline_rounded),
                            label: const Text('Preview'),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: FilledButton.icon(
                            onPressed: saveBusy
                                ? null
                                : () {
                                    if (lockedPremium) {
                                      _showMessage(
                                        'Upgrade your plan first to save premium scenes.',
                                      );
                                      return;
                                    }
                                    _saveScene(item);
                                  },
                            icon: saveBusy
                                ? const SizedBox(
                                    width: 16,
                                    height: 16,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : Icon(
                                    lockedPremium
                                        ? Icons.workspace_premium_outlined
                                        : Icons.bedtime_rounded,
                                  ),
                            label: const Text('Save Tonight'),
                          ),
                        ),
                      ],
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
