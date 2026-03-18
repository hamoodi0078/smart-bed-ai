import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/models.dart';
import '../../state/mobile_data.dart';
import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class BedControlsScreen extends ConsumerStatefulWidget {
  const BedControlsScreen({super.key});

  @override
  ConsumerState<BedControlsScreen> createState() => _BedControlsScreenState();
}

class _BedControlsScreenState extends ConsumerState<BedControlsScreen> {
  DeviceControls? _controls;
  bool _didHydrate = false;
  bool _saving = false;
  bool _commandBusy = false;
  bool _dirty = false;
  String _selectedColor = '#00D4FF';

  static const List<String> _colorPresets = <String>[
    '#00D4FF',
    '#FFFFFF',
    '#7B68EE',
    '#FF6B35',
    '#22C55E',
    '#FFD700',
  ];

  void _hydrate(DeviceControls controls) {
    if (_didHydrate && _dirty) {
      return;
    }
    _didHydrate = true;
    _controls = controls;
  }

  Future<void> _refresh() async {
    ref.invalidate(deviceControlsProvider);
    await ref.read(deviceControlsProvider.future);
  }

  Future<void> _saveControls() async {
    final current = _controls;
    if (current == null) {
      return;
    }
    setState(() {
      _saving = true;
    });
    try {
      final saved = await ref
          .read(smartBedRepositoryProvider)
          .saveDeviceControls(current);
      if (!mounted) {
        return;
      }
      setState(() {
        _controls = saved;
        _dirty = false;
      });
      ref.invalidate(bedStateProvider);
      ref.invalidate(dashboardBundleProvider);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Bed controls updated.')),
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
          _saving = false;
        });
      }
    }
  }

  Future<void> _runAction(String action) async {
    setState(() {
      _commandBusy = true;
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
      ref.invalidate(timelineFeedProvider);
      ref.invalidate(dashboardBundleProvider);
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
          _commandBusy = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final controlsAsync = ref.watch(deviceControlsProvider);
    final controls = controlsAsync.valueOrNull;
    final error = controlsAsync.error;

    if (controls != null) {
      _hydrate(controls);
    }
    final current = _controls;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        title: const Text('Bed Controls'),
        actions: <Widget>[
          IconButton(
            onPressed: _refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: current == null
          ? Center(
              child: error == null
                  ? const CircularProgressIndicator()
                  : PanelCard(
                      child: Padding(
                        padding: const EdgeInsets.all(20),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: <Widget>[
                            Text(
                              error is ApiException
                                  ? error.message
                                  : 'Unable to load bed controls.',
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 14),
                            FilledButton(
                              onPressed: _refresh,
                              child: const Text('Retry'),
                            ),
                          ],
                        ),
                      ),
                    ),
            )
          : RefreshIndicator(
              onRefresh: _refresh,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
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
                        Text('LED and audio', style: theme.textTheme.headlineMedium),
                        const SizedBox(height: 8),
                        Text(
                          'This screen is the active mobile control center for lights, brightness, alarm relay, and automation shortcuts.',
                          style: theme.textTheme.bodyLarge,
                        ),
                        const SizedBox(height: 14),
                        Wrap(
                          spacing: 10,
                          runSpacing: 10,
                          children: <Widget>[
                            StatusPill(
                              label: current.lightsOn ? 'Lights on' : 'Lights off',
                              tone: current.lightsOn
                                  ? StatusTone.success
                                  : StatusTone.neutral,
                            ),
                            StatusPill(
                              label: current.audioOn ? 'Audio on' : 'Audio off',
                              tone: current.audioOn
                                  ? StatusTone.info
                                  : StatusTone.neutral,
                            ),
                            StatusPill(
                              label: current.alarmOn ? 'Alarm armed' : 'Alarm muted',
                              tone: current.alarmOn
                                  ? StatusTone.warning
                                  : StatusTone.neutral,
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  PanelCard(
                    child: Column(
                      children: <Widget>[
                        SwitchListTile.adaptive(
                          value: current.lightsOn,
                          title: const Text('Bed LEDs'),
                          subtitle: const Text('Main lighting strip power.'),
                          contentPadding: EdgeInsets.zero,
                          onChanged: (value) {
                            setState(() {
                              _controls = current.copyWith(lightsOn: value);
                              _dirty = true;
                            });
                          },
                        ),
                        SwitchListTile.adaptive(
                          value: current.audioOn,
                          title: const Text('Ambient audio'),
                          subtitle: const Text('Bed speaker output'),
                          contentPadding: EdgeInsets.zero,
                          onChanged: (value) {
                            setState(() {
                              _controls = current.copyWith(audioOn: value);
                              _dirty = true;
                            });
                          },
                        ),
                        SwitchListTile.adaptive(
                          value: current.alarmOn,
                          title: const Text('Alarm relay'),
                          subtitle: const Text('Allow wake alarms through bed audio.'),
                          contentPadding: EdgeInsets.zero,
                          onChanged: (value) {
                            setState(() {
                              _controls = current.copyWith(alarmOn: value);
                              _dirty = true;
                            });
                          },
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: <Widget>[
                            Expanded(
                              child: Text(
                                'Brightness: ${current.lightLevel}%',
                                style: theme.textTheme.titleMedium,
                              ),
                            ),
                            StatusPill(label: '${current.lightLevel}%', tone: StatusTone.info),
                          ],
                        ),
                        Slider(
                          value: current.lightLevel.toDouble(),
                          min: 0,
                          max: 100,
                          divisions: 20,
                          onChanged: (value) {
                            setState(() {
                              _controls = current.copyWith(lightLevel: value.round());
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
                        Text('Color presets', style: theme.textTheme.titleLarge),
                        const SizedBox(height: 10),
                        Text(
                          'Preset tap changes the active scene color profile target.',
                          style: theme.textTheme.bodyMedium,
                        ),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 12,
                          runSpacing: 12,
                          children: _colorPresets.map((hex) {
                            final selected = _selectedColor == hex;
                            return GestureDetector(
                              onTap: () => setState(() => _selectedColor = hex),
                              child: Container(
                                width: 38,
                                height: 38,
                                decoration: BoxDecoration(
                                  color: _colorFromHex(hex),
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: selected
                                        ? SmartBedPalette.accent
                                        : Colors.transparent,
                                    width: 2,
                                  ),
                                ),
                              ),
                            );
                          }).toList(growable: false),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  PanelCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text('Automation shortcuts', style: theme.textTheme.titleLarge),
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 12,
                          runSpacing: 12,
                          children: <Widget>[
                            FilledButton.tonalIcon(
                              onPressed: _commandBusy
                                  ? null
                                  : () => _runAction('reactive_lights'),
                              icon: const Icon(Icons.multitrack_audio_rounded),
                              label: const Text('Reactive lights'),
                            ),
                            FilledButton.tonalIcon(
                              onPressed: _commandBusy
                                  ? null
                                  : () => _runAction('quiet_hours_override'),
                              icon: const Icon(Icons.bedtime_rounded),
                              label: const Text('Quiet override'),
                            ),
                            FilledButton.tonalIcon(
                              onPressed: _commandBusy
                                  ? null
                                  : () => _runAction('wake_recovery'),
                              icon: const Icon(Icons.wb_sunny_rounded),
                              label: const Text('Wake recovery'),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 18),
                  FilledButton.icon(
                    onPressed: _dirty && !_saving ? _saveControls : null,
                    icon: _saving
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.save_outlined),
                    label: const Text('Apply controls'),
                  ),
                ],
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
