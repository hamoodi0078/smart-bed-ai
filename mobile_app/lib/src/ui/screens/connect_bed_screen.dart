import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/api_client.dart';
import '../../state/mobile_data.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class ConnectBedScreen extends ConsumerStatefulWidget {
  const ConnectBedScreen({super.key});

  @override
  ConsumerState<ConnectBedScreen> createState() => _ConnectBedScreenState();
}

class _ConnectBedScreenState extends ConsumerState<ConnectBedScreen> {
  final TextEditingController _deviceIdController = TextEditingController();
  final TextEditingController _claimTokenController = TextEditingController();

  bool _busy = false;
  bool _scannerEnabled = false;
  bool _scanLocked = false;

  @override
  void dispose() {
    _deviceIdController.dispose();
    _claimTokenController.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    ref.invalidate(mobileDeviceInfoProvider);
    ref.invalidate(bedPairingStatusProvider);
    await Future.wait<void>(<Future<void>>[
      ref.read(mobileDeviceInfoProvider.future).then((_) {}),
      ref.read(bedPairingStatusProvider.future).then((_) {}),
    ]);
  }

  Future<void> _pair({String qrPayload = ''}) async {
    final deviceId = _deviceIdController.text.trim();
    final claimToken = _claimTokenController.text.trim();
    if (deviceId.isEmpty && qrPayload.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Scan a QR code or enter a device ID.')),
      );
      return;
    }

    setState(() {
      _busy = true;
    });
    try {
      final result = await ref.read(smartBedRepositoryProvider).pairBed(
            qrPayload: qrPayload,
            deviceId: deviceId,
            claimToken: claimToken,
          );
      if (!mounted) {
        return;
      }
      _deviceIdController.text = result.deviceId;
      await _refresh();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Bed paired: ${result.deviceId}')),
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
          _scanLocked = false;
        });
      }
    }
  }

  Future<void> _unpair(String deviceId) async {
    if (deviceId.trim().isEmpty) {
      return;
    }
    setState(() {
      _busy = true;
    });
    try {
      await ref.read(smartBedRepositoryProvider).unpairBed(deviceId: deviceId);
      if (!mounted) {
        return;
      }
      await _refresh();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Bed unpaired.')),
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

  Future<void> _onScanBarcode(BarcodeCapture capture) async {
    if (_scanLocked || _busy) {
      return;
    }
    final code = capture.barcodes.isNotEmpty
        ? (capture.barcodes.first.rawValue?.trim() ?? '')
        : '';
    if (code.isEmpty) {
      return;
    }
    setState(() {
      _scanLocked = true;
      _scannerEnabled = false;
    });
    await _pair(qrPayload: code);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final deviceAsync = ref.watch(mobileDeviceInfoProvider);
    final pairingAsync = ref.watch(bedPairingStatusProvider);
    final device = deviceAsync.valueOrNull;
    final pairing = pairingAsync.valueOrNull;
    final error = pairingAsync.error ?? deviceAsync.error;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        title: const Text('Connect Bed'),
        actions: <Widget>[
          IconButton(
            onPressed: _refresh,
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 120),
        children: <Widget>[
          PanelCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('Pair your bed', style: theme.textTheme.headlineMedium),
                const SizedBox(height: 8),
                Text(
                  'Use camera scan for QR labels or link manually using a device ID.',
                  style: theme.textTheme.bodyLarge,
                ),
                const SizedBox(height: 12),
                AnimatedContainer(
                  duration: const Duration(milliseconds: 180),
                  height: 220,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: theme.colorScheme.outline),
                  ),
                  clipBehavior: Clip.antiAlias,
                  child: _scannerEnabled
                      ? MobileScanner(
                          onDetect: _onScanBarcode,
                        )
                      : const Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: <Widget>[
                              Icon(Icons.qr_code_scanner_rounded, size: 52),
                              SizedBox(height: 10),
                              Text('Scanner paused'),
                            ],
                          ),
                        ),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: <Widget>[
                    FilledButton.tonalIcon(
                      onPressed: _busy
                          ? null
                          : () {
                              setState(() {
                                _scannerEnabled = !_scannerEnabled;
                                _scanLocked = false;
                              });
                            },
                      icon: Icon(
                        _scannerEnabled
                            ? Icons.qr_code_2_rounded
                            : Icons.qr_code_scanner_rounded,
                      ),
                      label: Text(_scannerEnabled ? 'Stop scanner' : 'Start scanner'),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _deviceIdController,
                  decoration: const InputDecoration(
                    labelText: 'Device ID',
                    hintText: 'DANA-KW-001-ABCD',
                    prefixIcon: Icon(Icons.memory_rounded),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _claimTokenController,
                  decoration: const InputDecoration(
                    labelText: 'Claim token (manual)',
                    hintText: 'Paste from provisioned QR payload',
                    prefixIcon: Icon(Icons.verified_user_outlined),
                  ),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: <Widget>[
                    FilledButton.icon(
                      onPressed: _busy ? null : () => _pair(),
                      icon: const Icon(Icons.link_rounded),
                      label: const Text('Pair manually'),
                    ),
                    if (pairing?.paired == true)
                      OutlinedButton.icon(
                        onPressed: _busy
                            ? null
                            : () => _unpair(pairing?.deviceId ?? ''),
                        icon: const Icon(Icons.link_off_rounded),
                        label: const Text('Unpair'),
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
                Text('Pairing status', style: theme.textTheme.titleLarge),
                const SizedBox(height: 10),
                if (error != null)
                  Text(
                    error is ApiException
                        ? error.message
                        : 'Unable to load pairing state.',
                    style: theme.textTheme.bodyMedium,
                  )
                else
                  Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: <Widget>[
                      StatusPill(
                        label: pairing?.paired == true
                            ? 'Paired'
                            : 'Not paired',
                        tone: pairing?.paired == true
                            ? StatusTone.success
                            : StatusTone.warning,
                      ),
                      if ((pairing?.deviceId ?? '').isNotEmpty)
                        StatusPill(
                          label: pairing!.deviceId,
                          tone: StatusTone.info,
                        ),
                      if ((pairing?.bedLocation ?? '').isNotEmpty)
                        StatusPill(
                          label: pairing!.bedLocation,
                          tone: StatusTone.neutral,
                        ),
                      if (pairing != null)
                        StatusPill(
                          label: pairing.provisioningVerified
                              ? 'Provisioning verified'
                              : 'Provisioning pending',
                          tone: pairing.provisioningVerified
                              ? StatusTone.success
                              : StatusTone.warning,
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
                Text('Live device info', style: theme.textTheme.titleLarge),
                const SizedBox(height: 10),
                if (device == null && deviceAsync.error == null)
                  const CircularProgressIndicator()
                else if (deviceAsync.error != null)
                  Text(
                    deviceAsync.error is ApiException
                        ? (deviceAsync.error as ApiException).message
                        : 'Unable to fetch device state.',
                    style: theme.textTheme.bodyMedium,
                  )
                else if (device != null)
                  Wrap(
                    spacing: 10,
                    runSpacing: 10,
                    children: <Widget>[
                      StatusPill(
                        label: device.online ? 'Device online' : 'Device offline',
                        tone: device.online
                            ? StatusTone.success
                            : StatusTone.warning,
                      ),
                      StatusPill(
                        label: 'Firmware ${device.firmwareVersion}',
                        tone: StatusTone.info,
                      ),
                      StatusPill(
                        label: 'Alarms ${device.alarmCount}',
                        tone: StatusTone.neutral,
                      ),
                      if (device.pairedDeviceId.isNotEmpty)
                        StatusPill(
                          label: device.provisioningVerified
                              ? 'Claim token verified'
                              : 'Claim token missing',
                          tone: device.provisioningVerified
                              ? StatusTone.success
                              : StatusTone.warning,
                        ),
                    ],
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
