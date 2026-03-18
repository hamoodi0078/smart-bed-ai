import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/device_connectivity_service.dart';
import '../../core/models.dart';
import '../../state/auth_controller.dart';
import '../../state/mobile_data.dart';
import '../../state/theme_controller.dart';
import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _displayNameController = TextEditingController();
  final _timezoneController = TextEditingController();
  final _cityController = TextEditingController();
  final _countryCodeController = TextEditingController();

  String _loadedSignature = '';
  String _responseStyle = 'balanced';
  String _engagementLevel = 'high';
  double _windDownMinutes = 45;
  bool _partnerModeEnabled = false;
  bool _bedtimeDriftAutomationEnabled = true;
  double _quietHoursOverrideLimitMinutes = 120;
  bool _weeklyInsightEnabled = true;
  bool _pushEnabled = true;
  bool _emailEnabled = false;
  String _locationMode = 'auto';
  String _themeMode = 'system';
  bool _saving = false;
  bool _dirty = false;
  bool _checkoutBusy = false;
  bool _subscriptionActionBusy = false;
  bool _handledCheckoutReturn = false;
  bool _connectivityLoading = false;
  bool _wifiActionBusy = false;
  bool _bluetoothActionBusy = false;
  bool _bluetoothSupported = false;
  bool _bluetoothEnabled = false;
  bool _bluetoothPermissionRequired = false;
  List<PairedBluetoothDevice> _pairedBluetoothDevices =
      const <PairedBluetoothDevice>[];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _handleCheckoutReturn();
      _refreshConnectivityState();
    });
  }

  @override
  void dispose() {
    _displayNameController.dispose();
    _timezoneController.dispose();
    _cityController.dispose();
    _countryCodeController.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    ref.invalidate(settingsBundleProvider);
    ref.invalidate(subscriptionStatusProvider);
    ref.invalidate(subscriptionHistoryProvider);
    await Future.wait<void>(<Future<void>>[
      ref.read(settingsBundleProvider.future).then((_) {}),
      ref.read(subscriptionStatusProvider.future).then((_) {}),
      ref.read(subscriptionHistoryProvider.future).then((_) {}),
    ]);
  }

  Future<void> _handleCheckoutReturn() async {
    if (_handledCheckoutReturn) {
      return;
    }
    final params = _paymentQueryParameters();
    final payment = params['payment']?.trim().toLowerCase() ?? '';
    if (payment.isEmpty) {
      return;
    }
    _handledCheckoutReturn = true;
    await _refresh();
    if (!mounted) {
      return;
    }
    final messenger = ScaffoldMessenger.of(context);
    if (payment == 'success') {
      messenger.showSnackBar(
        const SnackBar(
          content: Text('Payment confirmed. Subscription status refreshed.'),
        ),
      );
      return;
    }
    if (payment == 'pending') {
      messenger.showSnackBar(
        const SnackBar(
          content: Text(
            'Subscription approval returned, but PayPal is still finalizing activation.',
          ),
        ),
      );
      return;
    }
    if (payment == 'cancelled') {
      messenger.showSnackBar(
        const SnackBar(
          content: Text('Payment was cancelled. Your plan was not changed.'),
        ),
      );
    }
  }

  Future<void> _refreshConnectivityState({bool showFeedback = false}) async {
    setState(() {
      _connectivityLoading = true;
    });
    final service = ref.read(deviceConnectivityServiceProvider);
    final bluetoothState = await service.bluetoothState();
    final pairedSnapshot = await service.pairedBluetoothDevices();
    if (!mounted) {
      return;
    }
    setState(() {
      _bluetoothSupported =
          bluetoothState.supported || pairedSnapshot.supported;
      _bluetoothEnabled = bluetoothState.enabled;
      _bluetoothPermissionRequired =
          bluetoothState.permissionRequired ||
          pairedSnapshot.permissionRequired;
      _pairedBluetoothDevices = pairedSnapshot.devices;
      _connectivityLoading = false;
    });
    if (showFeedback) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            _pairedBluetoothDevices.isEmpty
                ? 'No paired Bluetooth devices found yet.'
                : 'Loaded ${_pairedBluetoothDevices.length} paired Bluetooth device(s).',
          ),
        ),
      );
    }
  }

  Future<void> _openWifiSettingsPanel() async {
    setState(() {
      _wifiActionBusy = true;
    });
    final launched = await ref
        .read(deviceConnectivityServiceProvider)
        .openWifiSettingsPanel();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            launched
                ? 'Opened Wi-Fi settings. Choose your network there.'
                : 'Wi-Fi settings are only available on Android devices.',
          ),
        ),
      );
      setState(() {
        _wifiActionBusy = false;
      });
    }
  }

  Future<void> _openBluetoothSettings() async {
    setState(() {
      _bluetoothActionBusy = true;
    });
    final launched = await ref
        .read(deviceConnectivityServiceProvider)
        .openBluetoothSettings();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            launched
                ? 'Opened Bluetooth settings. Pair your device, then return and refresh.'
                : 'Bluetooth settings are only available on Android devices.',
          ),
        ),
      );
      setState(() {
        _bluetoothActionBusy = false;
      });
    }
  }

  Map<String, String> _paymentQueryParameters() {
    if (Uri.base.queryParameters.isNotEmpty) {
      return Uri.base.queryParameters;
    }
    final fragment = Uri.base.fragment.trim();
    if (fragment.isEmpty) {
      return const <String, String>{};
    }
    final normalized = fragment.startsWith('/') ? fragment : '/$fragment';
    final fragmentUri = Uri.tryParse(normalized);
    if (fragmentUri == null) {
      return const <String, String>{};
    }
    return fragmentUri.queryParameters;
  }

  void _hydrate(SettingsBundle bundle) {
    final signature = _signatureFor(bundle);
    _displayNameController.text = bundle.profile.displayName;
    _timezoneController.text = bundle.profile.timezone;
    _cityController.text = bundle.profile.city;
    _countryCodeController.text = bundle.profile.countryCode;
    setState(() {
      _loadedSignature = signature;
      _responseStyle = bundle.settings.responseStyle;
      _engagementLevel = bundle.settings.engagementLevel;
      _windDownMinutes = bundle.settings.windDownMinutes.toDouble();
      _partnerModeEnabled = bundle.settings.partnerModeEnabled;
      _bedtimeDriftAutomationEnabled =
          bundle.settings.bedtimeDriftAutomationEnabled;
      _quietHoursOverrideLimitMinutes = bundle
          .settings
          .quietHoursOverrideLimitMinutes
          .toDouble();
      _weeklyInsightEnabled = bundle.settings.weeklyInsightEnabled;
      _pushEnabled = bundle.profile.pushEnabled;
      _emailEnabled = bundle.profile.emailEnabled;
      _locationMode = bundle.profile.locationMode;
      _themeMode = bundle.profile.themeMode;
      _dirty = false;
    });
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
    });

    final settings = UserSettings(
      responseStyle: _responseStyle,
      engagementLevel: _engagementLevel,
      partnerModeEnabled: _partnerModeEnabled,
      windDownMinutes: _windDownMinutes.round(),
      bedtimeDriftAutomationEnabled: _bedtimeDriftAutomationEnabled,
      quietHoursOverrideLimitMinutes: _quietHoursOverrideLimitMinutes.round(),
      weeklyInsightEnabled: _weeklyInsightEnabled,
    );
    final profile = UserProfilePrefs(
      displayName: _displayNameController.text.trim(),
      timezone: _timezoneController.text.trim().isEmpty
          ? 'Asia/Kuwait'
          : _timezoneController.text.trim(),
      pushEnabled: _pushEnabled,
      emailEnabled: _emailEnabled,
      locationMode: _locationMode,
      countryCode: _countryCodeController.text.trim().toUpperCase(),
      city: _cityController.text.trim(),
      latitude: null,
      longitude: null,
      themeMode: _themeMode,
    );

    try {
      final currentProfile = ref
          .read(settingsBundleProvider)
          .valueOrNull
          ?.profile;
      final bundle = await ref
          .read(smartBedRepositoryProvider)
          .saveSettingsBundle(
            settings: settings,
            profile: profile.copyWith(
              latitude: _locationMode == 'manual'
                  ? null
                  : currentProfile?.latitude,
              longitude: _locationMode == 'manual'
                  ? null
                  : currentProfile?.longitude,
              clearLatitude: _locationMode == 'manual',
              clearLongitude: _locationMode == 'manual',
            ),
          );
      await ref
          .read(themeControllerProvider.notifier)
          .applyRemoteTheme(bundle.profile.themeMode);
      _hydrate(bundle);
      ref.invalidate(dashboardBundleProvider);
      ref.invalidate(islamicOverviewProvider);
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Settings saved.')));
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.message)));
    } finally {
      if (mounted) {
        setState(() {
          _saving = false;
        });
      }
    }
  }

  Future<void> _startCheckout(String tier) async {
    setState(() {
      _checkoutBusy = true;
    });
    try {
      final checkout = await ref
          .read(smartBedRepositoryProvider)
          .startSubscriptionCheckout(
            tier: tier,
            interval: 'monthly',
            returnUrl: Uri.base.toString(),
            cancelUrl: Uri.base.toString(),
          );
      final launched = await launchUrl(Uri.parse(checkout.approveUrl));
      if (!launched && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Unable to open PayPal checkout.')),
        );
      }
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.message)));
    } finally {
      if (mounted) {
        setState(() {
          _checkoutBusy = false;
        });
      }
    }
  }

  Future<void> _logout() async {
    await ref.read(authControllerProvider.notifier).signOut();
    if (mounted) {
      context.go('/auth');
    }
  }

  Future<void> _pauseSubscription() async {
    setState(() {
      _subscriptionActionBusy = true;
    });
    try {
      final message = await ref
          .read(smartBedRepositoryProvider)
          .pauseActiveSubscription(reason: 'Paused from app settings');
      await _refresh();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.message)));
    } finally {
      if (mounted) {
        setState(() {
          _subscriptionActionBusy = false;
        });
      }
    }
  }

  Future<void> _cancelSubscription() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Cancel subscription?'),
          content: const Text(
            'This will stop renewal for your current PayPal subscription and downgrade your plan.',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Keep subscription'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('Cancel now'),
            ),
          ],
        );
      },
    );
    if (confirmed != true) {
      return;
    }
    setState(() {
      _subscriptionActionBusy = true;
    });
    try {
      final message = await ref
          .read(smartBedRepositoryProvider)
          .cancelActiveSubscription(reason: 'Cancelled from app settings');
      await _refresh();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error.message)));
    } finally {
      if (mounted) {
        setState(() {
          _subscriptionActionBusy = false;
        });
      }
    }
  }

  void _markDirty() {
    if (_dirty) {
      return;
    }
    setState(() {
      _dirty = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final authState = ref.watch(authControllerProvider);
    final settingsAsync = ref.watch(settingsBundleProvider);
    final subscriptionAsync = ref.watch(subscriptionStatusProvider);
    final historyAsync = ref.watch(subscriptionHistoryProvider);
    final bundle = settingsAsync.valueOrNull;
    final subscription = subscriptionAsync.valueOrNull;
    final history = historyAsync.valueOrNull ?? const <BillingHistoryEvent>[];
    final error = settingsAsync.error ?? subscriptionAsync.error;
    final historyError = historyAsync.error;

    if (bundle != null) {
      final signature = _signatureFor(bundle);
      if (signature != _loadedSignature) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) {
            _hydrate(bundle);
          }
        });
      }
    }

    if (bundle == null && error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: PanelCard(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  const Icon(Icons.settings_rounded, size: 36),
                  const SizedBox(height: 12),
                  Text(
                    error is ApiException
                        ? error.message
                        : 'Unable to load settings.',
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  FilledButton(onPressed: _refresh, child: const Text('Retry')),
                ],
              ),
            ),
          ),
        ),
      );
    }

    if (bundle == null || subscription == null) {
      return const Center(child: CircularProgressIndicator());
    }

    final resolvedName = bundle.profile.resolvedDisplayName(
      authState.session?.user ??
          const MobileUser(
            userId: '',
            email: 'user@example.com',
            name: 'User',
            clientName: '',
          ),
    );

    return ListView(
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
                      Text('Settings', style: theme.textTheme.headlineMedium),
                      const SizedBox(height: 8),
                      Text(
                        'Manage Dana personalization, theme mode, prayer location, and billing. Built by Dana Abuhalifa.',
                        style: theme.textTheme.bodyLarge,
                      ),
                      const SizedBox(height: 14),
                      Wrap(
                        spacing: 10,
                        runSpacing: 10,
                        children: <Widget>[
                          StatusPill(
                            label: 'Hi $resolvedName',
                            tone: StatusTone.info,
                          ),
                          StatusPill(
                            label: subscription.planTier.toUpperCase(),
                            tone: subscription.isPremiumLike
                                ? StatusTone.success
                                : StatusTone.warning,
                          ),
                          StatusPill(
                            label: _dirty ? 'Unsaved changes' : 'Saved',
                            tone: _dirty
                                ? StatusTone.warning
                                : StatusTone.success,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                _buildSection(
                  context,
                  title: 'App pages',
                  child: Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: <Widget>[
                      FilledButton.tonalIcon(
                        onPressed: () => context.go('/connect-bed'),
                        icon: const Icon(Icons.qr_code_scanner_rounded),
                        label: const Text('Connect bed'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => context.go('/controls'),
                        icon: const Icon(Icons.tune_rounded),
                        label: const Text('Bed controls'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => context.go('/spotify'),
                        icon: const Icon(Icons.music_note_rounded),
                        label: const Text('Spotify'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => context.go('/alarm'),
                        icon: const Icon(Icons.alarm_rounded),
                        label: const Text('Alarm'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => context.go('/profile'),
                        icon: const Icon(Icons.account_circle_outlined),
                        label: const Text('Profile'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => context.go('/subscription'),
                        icon: const Icon(Icons.workspace_premium_outlined),
                        label: const Text('Subscription'),
                      ),
                      FilledButton.tonalIcon(
                        onPressed: () => context.go('/about'),
                        icon: const Icon(Icons.info_outline_rounded),
                        label: const Text('About'),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                _buildSection(
                  context,
                  title: 'Profile',
                  child: Column(
                    children: <Widget>[
                      TextField(
                        controller: _displayNameController,
                        decoration: const InputDecoration(
                          labelText: 'Display name override',
                          hintText: 'Leave blank to use your first name',
                          prefixIcon: Icon(Icons.person_outline_rounded),
                        ),
                        onChanged: (_) => _markDirty(),
                      ),
                      const SizedBox(height: 14),
                      TextField(
                        controller: _timezoneController,
                        decoration: const InputDecoration(
                          labelText: 'Timezone',
                          hintText: 'Asia/Karachi',
                          prefixIcon: Icon(Icons.public_rounded),
                        ),
                        onChanged: (_) => _markDirty(),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                _buildSection(
                  context,
                  title: 'Theme',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      SegmentedButton<String>(
                        segments: const <ButtonSegment<String>>[
                          ButtonSegment<String>(
                            value: 'system',
                            label: Text('System'),
                            icon: Icon(Icons.settings_suggest_rounded),
                          ),
                          ButtonSegment<String>(
                            value: 'dark',
                            label: Text('Dark'),
                            icon: Icon(Icons.dark_mode_rounded),
                          ),
                          ButtonSegment<String>(
                            value: 'light',
                            label: Text('Light'),
                            icon: Icon(Icons.light_mode_rounded),
                          ),
                        ],
                        selected: <String>{_themeMode},
                        onSelectionChanged: (selection) {
                          setState(() {
                            _themeMode = selection.first;
                            _dirty = true;
                          });
                        },
                      ),
                      const SizedBox(height: 10),
                      Text(
                        'Theme mode is applied locally and synced to your account.',
                        style: theme.textTheme.bodyMedium,
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                _buildSection(
                  context,
                  title: 'Prayer location',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      SegmentedButton<String>(
                        segments: const <ButtonSegment<String>>[
                          ButtonSegment<String>(
                            value: 'auto',
                            label: Text('Auto'),
                            icon: Icon(Icons.my_location_rounded),
                          ),
                          ButtonSegment<String>(
                            value: 'manual',
                            label: Text('Manual'),
                            icon: Icon(Icons.edit_location_alt_rounded),
                          ),
                        ],
                        selected: <String>{_locationMode},
                        onSelectionChanged: (selection) {
                          setState(() {
                            _locationMode = selection.first;
                            _dirty = true;
                          });
                        },
                      ),
                      const SizedBox(height: 12),
                      Text(
                        _locationMode == 'auto'
                            ? 'Auto mode uses device location on login to calculate live prayer timings.'
                            : 'Manual mode lets you pin city, country code, and timezone for the bed.',
                        style: theme.textTheme.bodyMedium,
                      ),
                      if (_locationMode == 'manual') ...<Widget>[
                        const SizedBox(height: 14),
                        TextField(
                          controller: _cityController,
                          decoration: const InputDecoration(
                            labelText: 'City',
                            hintText: 'Karachi',
                            prefixIcon: Icon(Icons.location_city_rounded),
                          ),
                          onChanged: (_) => _markDirty(),
                        ),
                        const SizedBox(height: 14),
                        TextField(
                          controller: _countryCodeController,
                          decoration: const InputDecoration(
                            labelText: 'Country code',
                            hintText: 'PK',
                            prefixIcon: Icon(Icons.flag_outlined),
                          ),
                          onChanged: (_) => _markDirty(),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                _buildSection(
                  context,
                  title: 'Behavior',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      DropdownButtonFormField<String>(
                        initialValue: _responseStyle,
                        decoration: const InputDecoration(
                          labelText: 'Dana response style',
                        ),
                        items: const <DropdownMenuItem<String>>[
                          DropdownMenuItem(
                            value: 'balanced',
                            child: Text('Balanced'),
                          ),
                          DropdownMenuItem(
                            value: 'coaching',
                            child: Text('Coaching'),
                          ),
                          DropdownMenuItem(value: 'calm', child: Text('Calm')),
                        ],
                        onChanged: (value) {
                          if (value == null) {
                            return;
                          }
                          setState(() {
                            _responseStyle = value;
                            _dirty = true;
                          });
                        },
                      ),
                      const SizedBox(height: 14),
                      DropdownButtonFormField<String>(
                        initialValue: _engagementLevel,
                        decoration: const InputDecoration(
                          labelText: 'Engagement level',
                        ),
                        items: const <DropdownMenuItem<String>>[
                          DropdownMenuItem(value: 'high', child: Text('High')),
                          DropdownMenuItem(
                            value: 'medium',
                            child: Text('Medium'),
                          ),
                          DropdownMenuItem(value: 'low', child: Text('Low')),
                        ],
                        onChanged: (value) {
                          if (value == null) {
                            return;
                          }
                          setState(() {
                            _engagementLevel = value;
                            _dirty = true;
                          });
                        },
                      ),
                      const SizedBox(height: 18),
                      Text(
                        'Wind-down minutes: ${_windDownMinutes.round()}',
                        style: theme.textTheme.titleMedium,
                      ),
                      Slider(
                        value: _windDownMinutes,
                        min: 15,
                        max: 120,
                        divisions: 21,
                        label: '${_windDownMinutes.round()} min',
                        onChanged: (value) {
                          setState(() {
                            _windDownMinutes = value;
                            _dirty = true;
                          });
                        },
                      ),
                      SwitchListTile.adaptive(
                        value: _partnerModeEnabled,
                        title: const Text('Partner mode'),
                        subtitle: const Text(
                          'Keep the bed calmer when both sides are active.',
                        ),
                        contentPadding: EdgeInsets.zero,
                        onChanged: (value) {
                          setState(() {
                            _partnerModeEnabled = value;
                            _dirty = true;
                          });
                        },
                      ),
                      SwitchListTile.adaptive(
                        value: _bedtimeDriftAutomationEnabled,
                        title: const Text('Bedtime drift automation'),
                        subtitle: const Text(
                          'Surface predictive drift alerts in home and report.',
                        ),
                        contentPadding: EdgeInsets.zero,
                        onChanged: (value) {
                          setState(() {
                            _bedtimeDriftAutomationEnabled = value;
                            _dirty = true;
                          });
                        },
                      ),
                      Text(
                        'Quiet-hours override cap: ${_quietHoursOverrideLimitMinutes.round()} min',
                        style: theme.textTheme.titleMedium,
                      ),
                      Slider(
                        value: _quietHoursOverrideLimitMinutes,
                        min: 30,
                        max: 240,
                        divisions: 21,
                        label: '${_quietHoursOverrideLimitMinutes.round()} min',
                        onChanged: (value) {
                          setState(() {
                            _quietHoursOverrideLimitMinutes = value;
                            _dirty = true;
                          });
                        },
                      ),
                      SwitchListTile.adaptive(
                        value: _weeklyInsightEnabled,
                        title: const Text('Weekly insights'),
                        subtitle: const Text(
                          'Show Dana weekly coaching and recovery notes.',
                        ),
                        contentPadding: EdgeInsets.zero,
                        onChanged: (value) {
                          setState(() {
                            _weeklyInsightEnabled = value;
                            _dirty = true;
                          });
                        },
                      ),
                      SwitchListTile.adaptive(
                        value: _pushEnabled,
                        title: const Text('Push notifications'),
                        subtitle: const Text(
                          'Prayer reminders, wind-down prompts, and morning nudges.',
                        ),
                        contentPadding: EdgeInsets.zero,
                        onChanged: (value) {
                          setState(() {
                            _pushEnabled = value;
                            _dirty = true;
                          });
                        },
                      ),
                      SwitchListTile.adaptive(
                        value: _emailEnabled,
                        title: const Text('Email summaries'),
                        subtitle: const Text(
                          'Weekly sleep summaries and account notices.',
                        ),
                        contentPadding: EdgeInsets.zero,
                        onChanged: (value) {
                          setState(() {
                            _emailEnabled = value;
                            _dirty = true;
                          });
                        },
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                _buildSection(
                  context,
                  title: 'Device connectivity',
                  child: _buildConnectivitySection(context),
                ),
                const SizedBox(height: 18),
                _buildSection(
                  context,
                  title: 'Billing',
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        'Current plan: ${subscription.planTier.toUpperCase()} · KD ${subscription.priceKwd.toStringAsFixed(2)}/mo',
                        style: theme.textTheme.titleMedium,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Web checkout uses PayPal first. Native store billing can be layered in later.',
                        style: theme.textTheme.bodyMedium,
                      ),
                      const SizedBox(height: 14),
                      Wrap(
                        spacing: 12,
                        runSpacing: 12,
                        children: <Widget>[
                          StatusPill(
                            label: subscription.providerStatus.isEmpty
                                ? subscription.status.toUpperCase()
                                : subscription.providerStatus.toUpperCase(),
                            tone: subscription.status == 'active'
                                ? StatusTone.success
                                : subscription.status == 'grace'
                                ? StatusTone.warning
                                : StatusTone.neutral,
                          ),
                          if (subscription.nextRenewalAt.isNotEmpty)
                            StatusPill(
                              label:
                                  'Renews ${_shortDate(subscription.nextRenewalAt)}',
                              tone: StatusTone.info,
                            ),
                          if (subscription.lastPaymentAt.isNotEmpty)
                            StatusPill(
                              label:
                                  'Paid ${_shortDate(subscription.lastPaymentAt)}',
                              tone: StatusTone.neutral,
                            ),
                        ],
                      ),
                      const SizedBox(height: 14),
                      if (subscription.providerSubscriptionId.isNotEmpty)
                        SelectableText(
                          'Subscription ID: ${subscription.providerSubscriptionId}',
                          style: theme.textTheme.bodySmall,
                        ),
                      if (subscription.providerPlanId.isNotEmpty) ...<Widget>[
                        const SizedBox(height: 6),
                        SelectableText(
                          'PayPal plan: ${subscription.providerPlanId}',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                      const SizedBox(height: 14),
                      Wrap(
                        spacing: 12,
                        runSpacing: 12,
                        children: <Widget>[
                          FilledButton.tonal(
                            onPressed: _checkoutBusy
                                ? null
                                : () => _startCheckout('standard'),
                            child: const Text('Upgrade to Premium · KD 4.90'),
                          ),
                          FilledButton(
                            onPressed: _checkoutBusy
                                ? null
                                : () => _startCheckout('pro'),
                            child: _checkoutBusy
                                ? const SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Text('Upgrade to Pro · KD 9.90'),
                          ),
                          if (subscription.providerSubscriptionId.isNotEmpty &&
                              subscription.status == 'active')
                            OutlinedButton.icon(
                              onPressed: _subscriptionActionBusy
                                  ? null
                                  : _pauseSubscription,
                              icon: const Icon(
                                Icons.pause_circle_outline_rounded,
                              ),
                              label: const Text('Pause subscription'),
                            ),
                          if (subscription.providerSubscriptionId.isNotEmpty &&
                              subscription.status != 'inactive')
                            OutlinedButton.icon(
                              onPressed: _subscriptionActionBusy
                                  ? null
                                  : _cancelSubscription,
                              icon: const Icon(Icons.cancel_outlined),
                              label: _subscriptionActionBusy
                                  ? const SizedBox(
                                      width: 16,
                                      height: 16,
                                      child: CircularProgressIndicator(
                                        strokeWidth: 2,
                                      ),
                                    )
                                  : const Text('Cancel subscription'),
                            ),
                        ],
                      ),
                      const SizedBox(height: 18),
                      Text(
                        'Recent billing events',
                        style: theme.textTheme.titleMedium,
                      ),
                      const SizedBox(height: 10),
                      if (historyAsync.isLoading && history.isEmpty)
                        const Padding(
                          padding: EdgeInsets.symmetric(vertical: 12),
                          child: LinearProgressIndicator(minHeight: 3),
                        )
                      else if (historyError != null)
                        Text(
                          historyError is ApiException
                              ? historyError.message
                              : 'Unable to load billing history right now.',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: SmartBedPalette.warning,
                          ),
                        )
                      else if (history.isEmpty)
                        Text(
                          'No billing events yet. Your PayPal subscription activity will appear here after the first approval.',
                          style: theme.textTheme.bodyMedium,
                        )
                      else
                        Column(
                          children: history
                              .map((event) {
                                final tone = event.isFailure
                                    ? StatusTone.warning
                                    : event.isSuccess
                                    ? StatusTone.success
                                    : StatusTone.info;
                                return Padding(
                                  padding: const EdgeInsets.only(bottom: 12),
                                  child: Container(
                                    padding: const EdgeInsets.all(14),
                                    decoration: BoxDecoration(
                                      color: SmartBedPalette.surfaceAlt(
                                        theme.brightness,
                                      ).withValues(alpha: 0.54),
                                      borderRadius: BorderRadius.circular(20),
                                      border: Border.all(
                                        color: SmartBedPalette.accent
                                            .withValues(alpha: 0.10),
                                      ),
                                    ),
                                    child: Row(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: <Widget>[
                                        StatusPill(
                                          label: event.status.isEmpty
                                              ? event.eventType.toUpperCase()
                                              : event.status.toUpperCase(),
                                          tone: tone,
                                        ),
                                        const SizedBox(width: 12),
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment:
                                                CrossAxisAlignment.start,
                                            children: <Widget>[
                                              Text(
                                                event.summary,
                                                style:
                                                    theme.textTheme.titleMedium,
                                              ),
                                              const SizedBox(height: 4),
                                              Text(
                                                _billingEventDetails(event),
                                                style:
                                                    theme.textTheme.bodySmall,
                                              ),
                                            ],
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              })
                              .toList(growable: false),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 18),
                FilledButton.icon(
                  onPressed: _saving ? null : _save,
                  icon: _saving
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.save_outlined),
                  label: const Text('Save settings'),
                ),
                const SizedBox(height: 10),
                OutlinedButton.icon(
                  onPressed: _logout,
                  icon: const Icon(Icons.logout_rounded),
                  label: const Text('Sign out'),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildConnectivitySection(BuildContext context) {
    final theme = Theme.of(context);
    final bluetoothTone = !_bluetoothSupported
        ? StatusTone.neutral
        : _bluetoothEnabled
        ? StatusTone.success
        : StatusTone.warning;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          'Set up your bed network and pair nearby Bluetooth accessories from one place.',
          style: theme.textTheme.bodyMedium,
        ),
        const SizedBox(height: 14),
        Wrap(
          spacing: 10,
          runSpacing: 10,
          children: <Widget>[
            StatusPill(
              label: _bluetoothSupported
                  ? (_bluetoothEnabled ? 'Bluetooth on' : 'Bluetooth off')
                  : 'Bluetooth unavailable',
              tone: bluetoothTone,
            ),
            StatusPill(
              label: '${_pairedBluetoothDevices.length} paired',
              tone: StatusTone.info,
            ),
            if (_bluetoothPermissionRequired)
              const StatusPill(
                label: 'Bluetooth permission needed',
                tone: StatusTone.warning,
              ),
          ],
        ),
        const SizedBox(height: 14),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: <Widget>[
            FilledButton.icon(
              onPressed: _wifiActionBusy ? null : _openWifiSettingsPanel,
              icon: _wifiActionBusy
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.wifi_rounded),
              label: const Text('Change Wi-Fi network'),
            ),
            OutlinedButton.icon(
              onPressed: _bluetoothActionBusy ? null : _openBluetoothSettings,
              icon: _bluetoothActionBusy
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.bluetooth_searching_rounded),
              label: const Text('Open Bluetooth settings'),
            ),
            FilledButton.tonalIcon(
              onPressed: _connectivityLoading
                  ? null
                  : () => _refreshConnectivityState(showFeedback: true),
              icon: _connectivityLoading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh_rounded),
              label: const Text('Refresh paired devices'),
            ),
          ],
        ),
        const SizedBox(height: 14),
        if (_bluetoothPermissionRequired)
          Text(
            'Android 12+ requires Bluetooth permission. Use Bluetooth settings, allow access, then refresh here.',
            style: theme.textTheme.bodySmall?.copyWith(
              color: SmartBedPalette.warning,
            ),
          )
        else if (_pairedBluetoothDevices.isEmpty)
          Text(
            'No paired Bluetooth devices yet. Pair your bed accessory in Bluetooth settings first.',
            style: theme.textTheme.bodySmall,
          )
        else
          Column(
            children: _pairedBluetoothDevices
                .take(6)
                .map((device) {
                  final title = device.name.isEmpty
                      ? 'Unnamed device'
                      : device.name;
                  final subtitle = device.address.isEmpty
                      ? 'Paired device'
                      : '${device.address} · Bond state ${device.bondState}';
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 14,
                        vertical: 12,
                      ),
                      decoration: BoxDecoration(
                        color: SmartBedPalette.surfaceAlt(
                          theme.brightness,
                        ).withValues(alpha: 0.45),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: SmartBedPalette.accent.withValues(alpha: 0.10),
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(title, style: theme.textTheme.titleMedium),
                          const SizedBox(height: 4),
                          Text(subtitle, style: theme.textTheme.bodySmall),
                        ],
                      ),
                    ),
                  );
                })
                .toList(growable: false),
          ),
      ],
    );
  }

  Widget _buildSection(
    BuildContext context, {
    required String title,
    required Widget child,
  }) {
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 16),
          child,
        ],
      ),
    );
  }
}

String _signatureFor(SettingsBundle bundle) {
  return <Object?>[
    bundle.profile.displayName,
    bundle.profile.timezone,
    bundle.profile.pushEnabled,
    bundle.profile.emailEnabled,
    bundle.profile.locationMode,
    bundle.profile.countryCode,
    bundle.profile.city,
    bundle.profile.latitude,
    bundle.profile.longitude,
    bundle.profile.themeMode,
    bundle.settings.responseStyle,
    bundle.settings.engagementLevel,
    bundle.settings.partnerModeEnabled,
    bundle.settings.windDownMinutes,
    bundle.settings.bedtimeDriftAutomationEnabled,
    bundle.settings.quietHoursOverrideLimitMinutes,
    bundle.settings.weeklyInsightEnabled,
  ].join('|');
}

String _shortDate(String value) {
  final raw = value.trim();
  if (raw.isEmpty) {
    return '';
  }
  final parsed = DateTime.tryParse(raw);
  if (parsed == null) {
    return raw;
  }
  final local = parsed.toLocal();
  final year = local.year.toString().padLeft(4, '0');
  final month = local.month.toString().padLeft(2, '0');
  final day = local.day.toString().padLeft(2, '0');
  return '$year-$month-$day';
}

String _billingEventDetails(BillingHistoryEvent event) {
  final parts = <String>[
    _shortDate(event.createdAt),
    if (event.amountValue.isNotEmpty)
      '${event.currency.isEmpty ? '' : '${event.currency} '}${event.amountValue}',
    if (event.providerReference.isNotEmpty) 'Ref ${event.providerReference}',
    if (event.tier.isNotEmpty) '${event.tier.toUpperCase()} ${event.interval}',
  ];
  return parts.where((part) => part.trim().isNotEmpty).join(' · ');
}
