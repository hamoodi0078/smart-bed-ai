import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../state/mobile_data.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class SubscriptionScreen extends ConsumerStatefulWidget {
  const SubscriptionScreen({super.key});

  @override
  ConsumerState<SubscriptionScreen> createState() => _SubscriptionScreenState();
}

class _SubscriptionScreenState extends ConsumerState<SubscriptionScreen> {
  bool _busy = false;

  Future<void> _refresh() async {
    ref.invalidate(subscriptionStatusProvider);
    ref.invalidate(subscriptionHistoryProvider);
    await Future.wait<void>(<Future<void>>[
      ref.read(subscriptionStatusProvider.future).then((_) {}),
      ref.read(subscriptionHistoryProvider.future).then((_) {}),
    ]);
  }

  Future<void> _startCheckout() async {
    setState(() {
      _busy = true;
    });
    try {
      final checkout = await ref
          .read(smartBedRepositoryProvider)
          .startSubscriptionCheckout(tier: 'pro', interval: 'monthly');
      final url = checkout.approveUrl.trim();
      if (url.isEmpty) {
        throw const ApiException(message: 'Checkout URL is unavailable.');
      }
      await launchUrl(
        Uri.parse(url),
        mode: LaunchMode.externalApplication,
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Checkout opened in browser.')),
      );
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
          _busy = false;
        });
      }
    }
  }

  Future<void> _pause() async {
    setState(() {
      _busy = true;
    });
    try {
      final message = await ref
          .read(smartBedRepositoryProvider)
          .pauseActiveSubscription(reason: 'Paused from mobile subscription page');
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
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
          _busy = false;
        });
      }
    }
  }

  Future<void> _cancel() async {
    setState(() {
      _busy = true;
    });
    try {
      final message = await ref
          .read(smartBedRepositoryProvider)
          .cancelActiveSubscription(reason: 'Cancelled from mobile subscription page');
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(message)),
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
          _busy = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final statusAsync = ref.watch(subscriptionStatusProvider);
    final historyAsync = ref.watch(subscriptionHistoryProvider);
    final status = statusAsync.valueOrNull;
    final history = historyAsync.valueOrNull ?? const <BillingHistoryEvent>[];
    final error = statusAsync.error ?? historyAsync.error;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        title: const Text('Subscription'),
        actions: <Widget>[
          IconButton(
            onPressed: _refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: status == null
          ? Center(
              child: error == null
                  ? const CircularProgressIndicator()
                  : PanelCard(
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Text(
                          error is ApiException
                              ? error.message
                              : 'Unable to load subscription status.',
                        ),
                      ),
                    ),
            )
          : ListView(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
              children: <Widget>[
                PanelCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text('Plan status', style: theme.textTheme.headlineMedium),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: <Widget>[
                          StatusPill(
                            label: status.planTier.toUpperCase(),
                            tone: status.isPremiumLike
                                ? StatusTone.success
                                : StatusTone.warning,
                          ),
                          StatusPill(
                            label: status.status.toUpperCase(),
                            tone: status.status == 'active'
                                ? StatusTone.info
                                : StatusTone.neutral,
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      Text(
                        'KWD ${status.priceKwd.toStringAsFixed(2)} / month',
                        style: theme.textTheme.titleLarge,
                      ),
                      if (status.nextRenewalAt.isNotEmpty) ...<Widget>[
                        const SizedBox(height: 4),
                        Text(
                          'Next renewal: ${status.nextRenewalAt}',
                          style: theme.textTheme.bodyMedium,
                        ),
                      ],
                      const SizedBox(height: 14),
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: <Widget>[
                          FilledButton.icon(
                            onPressed: _busy ? null : _startCheckout,
                            icon: const Icon(Icons.upgrade_rounded),
                            label: const Text('Upgrade'),
                          ),
                          OutlinedButton.icon(
                            onPressed: _busy ? null : _pause,
                            icon: const Icon(Icons.pause_circle_outline_rounded),
                            label: const Text('Pause'),
                          ),
                          OutlinedButton.icon(
                            onPressed: _busy ? null : _cancel,
                            icon: const Icon(Icons.cancel_outlined),
                            label: const Text('Cancel'),
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
                      Text('Billing history', style: theme.textTheme.titleLarge),
                      const SizedBox(height: 10),
                      if (history.isEmpty)
                        Text(
                          'No billing events yet.',
                          style: theme.textTheme.bodyMedium,
                        )
                      else
                        ...history.map((event) {
                          return ListTile(
                            contentPadding: EdgeInsets.zero,
                            title: Text(event.summary.isEmpty
                                ? event.eventType
                                : event.summary),
                            subtitle: Text(event.createdAt),
                            trailing: StatusPill(
                              label: event.eventType,
                              tone: event.isFailure
                                  ? StatusTone.danger
                                  : event.isSuccess
                                      ? StatusTone.success
                                      : StatusTone.neutral,
                            ),
                          );
                        }),
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}
