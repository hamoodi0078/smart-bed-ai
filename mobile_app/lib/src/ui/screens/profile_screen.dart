import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../state/mobile_data.dart';
import '../widgets/panel_card.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final _displayNameController = TextEditingController();
  final _timezoneController = TextEditingController();
  final _cityController = TextEditingController();
  final _countryCodeController = TextEditingController();

  bool _pushEnabled = true;
  bool _emailEnabled = false;
  bool _hydrated = false;
  bool _busy = false;

  @override
  void dispose() {
    _displayNameController.dispose();
    _timezoneController.dispose();
    _cityController.dispose();
    _countryCodeController.dispose();
    super.dispose();
  }

  void _hydrate(SettingsBundle bundle) {
    if (_hydrated) {
      return;
    }
    _hydrated = true;
    _displayNameController.text = bundle.profile.displayName;
    _timezoneController.text = bundle.profile.timezone;
    _cityController.text = bundle.profile.city;
    _countryCodeController.text = bundle.profile.countryCode;
    _pushEnabled = bundle.profile.pushEnabled;
    _emailEnabled = bundle.profile.emailEnabled;
  }

  Future<void> _save(SettingsBundle bundle) async {
    setState(() {
      _busy = true;
    });
    try {
      final profile = bundle.profile.copyWith(
        displayName: _displayNameController.text.trim(),
        timezone: _timezoneController.text.trim(),
        city: _cityController.text.trim(),
        countryCode: _countryCodeController.text.trim().toUpperCase(),
        pushEnabled: _pushEnabled,
        emailEnabled: _emailEnabled,
      );
      await ref.read(smartBedRepositoryProvider).saveSettingsBundle(
            settings: bundle.settings,
            profile: profile,
          );
      if (!mounted) {
        return;
      }
      ref.invalidate(settingsBundleProvider);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Profile saved.')),
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final bundleAsync = ref.watch(settingsBundleProvider);
    final bundle = bundleAsync.valueOrNull;
    final error = bundleAsync.error;

    if (bundle != null) {
      _hydrate(bundle);
    }

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        title: const Text('Profile'),
      ),
      body: bundle == null
          ? Center(
              child: error == null
                  ? const CircularProgressIndicator()
                  : PanelCard(
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Text(
                          error is ApiException
                              ? error.message
                              : 'Unable to load profile.',
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
                      Text('Account profile', style: theme.textTheme.headlineMedium),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _displayNameController,
                        decoration: const InputDecoration(
                          labelText: 'Display name',
                          prefixIcon: Icon(Icons.person_outline_rounded),
                        ),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _timezoneController,
                        decoration: const InputDecoration(
                          labelText: 'Timezone',
                          hintText: 'Asia/Kuwait',
                          prefixIcon: Icon(Icons.public_rounded),
                        ),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        children: <Widget>[
                          Expanded(
                            child: TextField(
                              controller: _cityController,
                              decoration: const InputDecoration(
                                labelText: 'City',
                                prefixIcon: Icon(Icons.location_city_rounded),
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          SizedBox(
                            width: 110,
                            child: TextField(
                              controller: _countryCodeController,
                              decoration: const InputDecoration(
                                labelText: 'Country',
                              ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      SwitchListTile.adaptive(
                        contentPadding: EdgeInsets.zero,
                        value: _pushEnabled,
                        onChanged: (value) {
                          setState(() {
                            _pushEnabled = value;
                          });
                        },
                        title: const Text('Push notifications'),
                      ),
                      SwitchListTile.adaptive(
                        contentPadding: EdgeInsets.zero,
                        value: _emailEnabled,
                        onChanged: (value) {
                          setState(() {
                            _emailEnabled = value;
                          });
                        },
                        title: const Text('Email updates'),
                      ),
                      const SizedBox(height: 14),
                      FilledButton.icon(
                        onPressed: _busy ? null : () => _save(bundle),
                        icon: const Icon(Icons.save_rounded),
                        label: const Text('Save profile'),
                      ),
                    ],
                  ),
                ),
              ],
            ),
    );
  }
}
