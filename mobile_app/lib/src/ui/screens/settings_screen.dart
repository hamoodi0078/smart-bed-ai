import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../config/app_config.dart';
import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../state/auth_controller.dart';
import '../../state/mobile_data.dart';
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
  bool _saving = false;
  bool _dirty = false;

  @override
  void dispose() {
    _displayNameController.dispose();
    _timezoneController.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    ref.invalidate(settingsBundleProvider);
    try {
      await ref.read(settingsBundleProvider.future);
    } catch (_) {}
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
      displayName: _displayNameController.text.trim().isEmpty
          ? 'User'
          : _displayNameController.text.trim(),
      timezone: _timezoneController.text.trim().isEmpty
          ? 'Asia/Kuwait'
          : _timezoneController.text.trim(),
      pushEnabled: _pushEnabled,
      emailEnabled: _emailEnabled,
    );

    try {
      final bundle = await ref
          .read(smartBedRepositoryProvider)
          .saveSettingsBundle(settings: settings, profile: profile);
      _hydrate(bundle);
      ref.invalidate(dashboardBundleProvider);
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

  Future<void> _logout() async {
    await ref.read(authControllerProvider.notifier).signOut();
    if (mounted) {
      context.go('/auth');
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

  void _hydrate(SettingsBundle bundle) {
    final signature = _signatureFor(bundle);
    _displayNameController.text = bundle.profile.displayName;
    _timezoneController.text = bundle.profile.timezone;
    setState(() {
      _loadedSignature = signature;
      _responseStyle = bundle.settings.responseStyle;
      _engagementLevel = bundle.settings.engagementLevel;
      _windDownMinutes = bundle.settings.windDownMinutes.toDouble();
      _partnerModeEnabled = bundle.settings.partnerModeEnabled;
      _bedtimeDriftAutomationEnabled =
          bundle.settings.bedtimeDriftAutomationEnabled;
      _quietHoursOverrideLimitMinutes =
          bundle.settings.quietHoursOverrideLimitMinutes.toDouble();
      _weeklyInsightEnabled = bundle.settings.weeklyInsightEnabled;
      _pushEnabled = bundle.profile.pushEnabled;
      _emailEnabled = bundle.profile.emailEnabled;
      _dirty = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final authState = ref.watch(authControllerProvider);
    final settingsAsync = ref.watch(settingsBundleProvider);
    final bundle = settingsAsync.valueOrNull;
    final error = settingsAsync.error;

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
          padding: const EdgeInsets.all(20),
          child: PanelCard(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                const Icon(Icons.settings_backup_restore_rounded, size: 36),
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
      );
    }

    if (bundle == null) {
      return const Center(child: CircularProgressIndicator());
    }

    return ListView(
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
              Text('Settings', style: theme.textTheme.headlineMedium),
              const SizedBox(height: 8),
              Text(
                'Tune the mobile surface, wind-down defaults, and notification preferences without expanding the old web UI.',
                style: theme.textTheme.bodyLarge,
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: <Widget>[
                  StatusPill(
                    label: authState.session?.user.email ?? '',
                    tone: StatusTone.info,
                  ),
                  StatusPill(
                    label: _dirty ? 'Unsaved changes' : 'Saved',
                    tone: _dirty ? StatusTone.warning : StatusTone.success,
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
              Text('Profile', style: theme.textTheme.titleLarge),
              const SizedBox(height: 16),
              TextField(
                controller: _displayNameController,
                decoration: const InputDecoration(labelText: 'Display name'),
                onChanged: (_) => _markDirty(),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: _timezoneController,
                decoration: const InputDecoration(labelText: 'Timezone'),
                onChanged: (_) => _markDirty(),
              ),
              const SizedBox(height: 14),
              SwitchListTile.adaptive(
                value: _pushEnabled,
                title: const Text('Push notifications'),
                subtitle: const Text(
                  'Keep bedtime and summary nudges on device.',
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
                title: const Text('Email backup summaries'),
                subtitle: const Text(
                  'Low-priority fallback for weekly reviews.',
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
        PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('Bed behavior', style: theme.textTheme.titleLarge),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                key: ValueKey<String>('response-style-$_responseStyle'),
                initialValue: _responseStyle,
                decoration: const InputDecoration(labelText: 'Response style'),
                items: const <DropdownMenuItem<String>>[
                  DropdownMenuItem(value: 'balanced', child: Text('Balanced')),
                  DropdownMenuItem(value: 'coaching', child: Text('Coaching')),
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
                key: ValueKey<String>('engagement-level-$_engagementLevel'),
                initialValue: _engagementLevel,
                decoration: const InputDecoration(
                  labelText: 'Engagement level',
                ),
                items: const <DropdownMenuItem<String>>[
                  DropdownMenuItem(value: 'high', child: Text('High')),
                  DropdownMenuItem(value: 'medium', child: Text('Medium')),
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
              Slider.adaptive(
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
                  'Keep motion and response behavior calmer at night.',
                ),
                contentPadding: EdgeInsets.zero,
                onChanged: (value) {
                  setState(() {
                    _partnerModeEnabled = value;
                    _dirty = true;
                  });
                },
              ),
              const SizedBox(height: 6),
              SwitchListTile.adaptive(
                value: _bedtimeDriftAutomationEnabled,
                title: const Text('Predictive bedtime drift automation'),
                subtitle: const Text(
                  'Show drift alerts in timeline and dashboard when bedtime starts sliding.',
                ),
                contentPadding: EdgeInsets.zero,
                onChanged: (value) {
                  setState(() {
                    _bedtimeDriftAutomationEnabled = value;
                    _dirty = true;
                  });
                },
              ),
              const SizedBox(height: 8),
              Text(
                'Quiet-hours override cap: ${_quietHoursOverrideLimitMinutes.round()} min',
                style: theme.textTheme.titleMedium,
              ),
              Slider.adaptive(
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
                title: const Text('Weekly insight coaching'),
                subtitle: const Text(
                  'Show weekly habit-loop coaching cards on the command center.',
                ),
                contentPadding: EdgeInsets.zero,
                onChanged: (value) {
                  setState(() {
                    _weeklyInsightEnabled = value;
                    _dirty = true;
                  });
                },
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('Runtime', style: theme.textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(
                'Local API base: ${AppConfig.apiBaseUrl}',
                style: theme.textTheme.bodyLarge,
              ),
              const SizedBox(height: 6),
              Text(
                'Use --dart-define=SMART_BED_API_BASE_URL=https://your-host for staging or device testing.',
                style: theme.textTheme.bodyMedium,
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
          label: const Text('Save changes'),
        ),
        const SizedBox(height: 10),
        OutlinedButton.icon(
          onPressed: _logout,
          icon: const Icon(Icons.logout_rounded),
          label: const Text('Sign out'),
        ),
      ],
    );
  }
}

String _signatureFor(SettingsBundle bundle) {
  return <Object?>[
    bundle.profile.displayName,
    bundle.profile.timezone,
    bundle.profile.pushEnabled,
    bundle.profile.emailEnabled,
    bundle.settings.responseStyle,
    bundle.settings.engagementLevel,
    bundle.settings.partnerModeEnabled,
    bundle.settings.windDownMinutes,
    bundle.settings.bedtimeDriftAutomationEnabled,
    bundle.settings.quietHoursOverrideLimitMinutes,
    bundle.settings.weeklyInsightEnabled,
  ].join('|');
}
