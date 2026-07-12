import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../state/mobile_data.dart';
import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class IslamicScreen extends ConsumerWidget {
  const IslamicScreen({super.key});

  Future<void> _refresh(WidgetRef ref) async {
    ref.invalidate(islamicOverviewProvider);
    await ref.read(islamicOverviewProvider.future);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overviewAsync = ref.watch(islamicOverviewProvider);

    return overviewAsync.when(
      data: (overview) => RefreshIndicator(
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
                          Text('Islamic Mode', style: Theme.of(context).textTheme.headlineMedium),
                          const SizedBox(height: 8),
                          Text(
                            'Live prayer timings are resolved from ${overview.location.label}. Dana keeps the bed calm around prayer time.',
                            style: Theme.of(context).textTheme.bodyLarge,
                          ),
                          const SizedBox(height: 14),
                          Wrap(
                            spacing: 10,
                            runSpacing: 10,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            children: <Widget>[
                              StatusPill(
                                label: overview.location.label,
                                tone: StatusTone.info,
                              ),
                              StatusPill(
                                label: overview.ramadanActive
                                    ? 'Ramadan active'
                                    : (overview.islamicEvent.isEmpty
                                    ? 'Daily guidance'
                                    : overview.islamicEvent),
                                tone: overview.ramadanActive
                                    ? StatusTone.success
                                    : StatusTone.neutral,
                              ),
                              const _UseMyLocationButton(),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),
                    LayoutBuilder(
                      builder: (context, constraints) {
                        final prayerCard = _PrayerTimesCard(overview: overview);
                        final nextPrayerCard = _NextPrayerCountdownCard(overview: overview);
                        if (constraints.maxWidth < 880) {
                          return Column(
                            children: <Widget>[
                              prayerCard,
                              const SizedBox(height: 18),
                              nextPrayerCard,
                            ],
                          );
                        }
                        return Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Expanded(child: prayerCard),
                            const SizedBox(width: 18),
                            Expanded(child: nextPrayerCard),
                          ],
                        );
                      },
                    ),
                    const SizedBox(height: 18),
                    LayoutBuilder(
                      builder: (context, constraints) {
                        final hadithCard = _HadithCard(overview: overview);
                        final calendarCard = _CalendarAndTipCard(overview: overview);
                        if (constraints.maxWidth < 880) {
                          return Column(
                            children: <Widget>[
                              hadithCard,
                              const SizedBox(height: 18),
                              calendarCard,
                            ],
                          );
                        }
                        return Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Expanded(child: hadithCard),
                            const SizedBox(width: 18),
                            Expanded(child: calendarCard),
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
      ),

      error: (error, stackTrace) {
        // 403 = premium required — show upgrade card instead of error
        final isPremiumError = (error is ApiException && error.statusCode == 403) ||
            error.toString().contains('403') ||
            error.toString().toLowerCase().contains('premium');
        if (isPremiumError) {
          return Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: const PanelCard(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Icon(Icons.star_rounded, size: 56, color: Colors.amber),
                      SizedBox(height: 16),
                      Text(
                        'Premium Feature',
                        style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                        textAlign: TextAlign.center,
                      ),
                      SizedBox(height: 10),
                      Text(
                        'Islamic Mode is available on the Premium plan. Upgrade to access prayer timings, Ramadan mode, and Tahajjud scheduling.',
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        }
        return _ErrorView(
          message: error is ApiException
              ? error.message
              : 'Unable to load Islamic mode.',
          onRetry: () => _refresh(ref),
        );
      },

      loading: () => const Center(child: CircularProgressIndicator()),
    );
  }
}

class _UseMyLocationButton extends ConsumerStatefulWidget {
  const _UseMyLocationButton();

  @override
  ConsumerState<_UseMyLocationButton> createState() =>
      _UseMyLocationButtonState();
}

class _UseMyLocationButtonState extends ConsumerState<_UseMyLocationButton> {
  bool _syncing = false;

  Future<void> _sync() async {
    if (_syncing) return;
    setState(() => _syncing = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final result =
          await ref.read(smartBedRepositoryProvider).syncDeviceLocation();
      if (!mounted) return;
      switch (result.status) {
        case LocationSyncStatus.updated:
          ref.invalidate(islamicOverviewProvider);
          messenger.showSnackBar(
            const SnackBar(
              content: Text('Prayer times now follow your location.'),
            ),
          );
        case LocationSyncStatus.unchanged:
          messenger.showSnackBar(
            const SnackBar(
              content: Text('Location already up to date.'),
            ),
          );
        case LocationSyncStatus.permissionDenied:
          messenger.showSnackBar(
            const SnackBar(
              content: Text(
                'Location permission is off. Allow it in your device settings '
                'so prayer times match where you are.',
              ),
            ),
          );
        case LocationSyncStatus.serviceDisabled:
          messenger.showSnackBar(
            const SnackBar(
              content: Text('Turn on location services to use this.'),
            ),
          );
        case LocationSyncStatus.failed:
          messenger.showSnackBar(
            const SnackBar(
              content: Text('Could not read your location — try again.'),
            ),
          );
      }
    } finally {
      if (mounted) setState(() => _syncing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      onPressed: _syncing ? null : _sync,
      icon: _syncing
          ? const SizedBox(
              width: 14,
              height: 14,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.my_location_rounded, size: 16),
      label: const Text('Use my location'),
      style: OutlinedButton.styleFrom(
        visualDensity: VisualDensity.compact,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      ),
    );
  }
}


class _PrayerTimesCard extends StatelessWidget {
  const _PrayerTimesCard({required this.overview});

  final IslamicOverview overview;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final prayers = overview.prayers.entries.toList(growable: false);
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Today\'s prayers', style: theme.textTheme.titleLarge),
          const SizedBox(height: 14),
          ...prayers.map((entry) {
            final isNext = entry.key == overview.nextPrayer.name;
            return Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: isNext
                    ? SmartBedPalette.accent.withValues(alpha: 0.10)
                    : SmartBedPalette.surfaceAlt(theme.brightness).withValues(alpha: 0.55),
                borderRadius: BorderRadius.circular(18),
              ),
              child: Row(
                children: <Widget>[
                  Expanded(child: Text(entry.key, style: theme.textTheme.titleMedium)),
                  Text(
                    entry.value,
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: isNext ? SmartBedPalette.accent : null,
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

class _NextPrayerCountdownCard extends StatelessWidget {
  const _NextPrayerCountdownCard({required this.overview});

  final IslamicOverview overview;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Prayer alert', style: theme.textTheme.titleLarge),
          const SizedBox(height: 14),
          Text(overview.nextPrayer.name, style: theme.textTheme.headlineMedium),
          const SizedBox(height: 6),
          Text(
            overview.nextPrayer.minutesUntil >= 0
                ? 'In ${overview.nextPrayer.minutesUntil} minutes'
                : 'Dana is syncing prayer timings.',
            style: theme.textTheme.bodyLarge,
          ),
          const SizedBox(height: 14),
          Row(
            children: <Widget>[
              Container(
                width: 18,
                height: 18,
                decoration: BoxDecoration(
                  color: _colorFromHex(overview.ledColor),
                  shape: BoxShape.circle,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Spotify pause and prayer LED scene are armed for ${overview.nextPrayer.name}.',
                  style: theme.textTheme.bodyMedium,
                ),
              ),
            ],
          ),
          const SizedBox(height: 18),
          StatusPill(
            label: overview.location.mode == 'manual' ? 'Manual location' : 'Auto location',
            tone: StatusTone.info,
          ),
        ],
      ),
    );
  }
}

class _HadithCard extends StatelessWidget {
  const _HadithCard({required this.overview});

  final IslamicOverview overview;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Today\'s hadith', style: theme.textTheme.titleLarge),
          const SizedBox(height: 14),
          Text(
            '${overview.hadith['hadith'] ?? ''}',
            style: theme.textTheme.bodyLarge?.copyWith(fontStyle: FontStyle.italic),
          ),
          const SizedBox(height: 10),
          Text('${overview.hadith['source'] ?? ''}', style: theme.textTheme.bodySmall),
          if ((overview.sleepHadith['hadith'] ?? '').toString().trim().isNotEmpty) ...<Widget>[
            const SizedBox(height: 18),
            Text('Sleep reminder', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              '${overview.sleepHadith['hadith'] ?? ''}',
              style: theme.textTheme.bodyMedium,
            ),
          ],
        ],
      ),
    );
  }
}

class _CalendarAndTipCard extends StatelessWidget {
  const _CalendarAndTipCard({required this.overview});

  final IslamicOverview overview;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hijriDate = overview.hijri['hijri_date']?.toString() ?? 'Unknown';
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('Hijri and Sunnah', style: theme.textTheme.titleLarge),
          const SizedBox(height: 14),
          Text(hijriDate, style: theme.textTheme.headlineSmall),
          const SizedBox(height: 6),
          Text(
            overview.islamicEvent.isEmpty
                ? (overview.ramadanActive ? 'Ramadan Kareem' : 'No special event today')
                : overview.islamicEvent,
            style: theme.textTheme.bodyLarge,
          ),
          const SizedBox(height: 16),
          Text('Tonight\'s Sunnah tip', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Text(overview.sunnahTip, style: theme.textTheme.bodyMedium),
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
                const Icon(Icons.mosque_rounded, size: 36),
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

Color _colorFromHex(String value) {
  final normalized = value.replaceAll('#', '').trim();
  if (normalized.length != 6) {
    return SmartBedPalette.accent;
  }
  return Color(int.parse('FF$normalized', radix: 16));
}