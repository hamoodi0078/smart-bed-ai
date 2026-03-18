import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:model_viewer_plus/model_viewer_plus.dart';

import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class BedViewerScreen extends StatefulWidget {
  const BedViewerScreen({super.key});

  @override
  State<BedViewerScreen> createState() => _BedViewerScreenState();
}

class _BedViewerScreenState extends State<BedViewerScreen> {
  double _yawDegrees = 35;
  double _pitchDegrees = 74;
  double _distanceMeters = 2.2;
  String _activeHotspot = 'Lighting rail';

  String get _cameraOrbit =>
      '${_yawDegrees.toStringAsFixed(0)}deg ${_pitchDegrees.toStringAsFixed(0)}deg ${_distanceMeters.toStringAsFixed(2)}m';

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isWide = MediaQuery.of(context).size.width >= 980;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        title: const Text('3D Bed Viewer'),
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 120),
          children: <Widget>[
            Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1180),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
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
                          Text('Danah Bed Visualizer', style: theme.textTheme.headlineMedium),
                          const SizedBox(height: 8),
                          Text(
                            'This pass now renders a real GLB asset and keeps hotspot bindings in the same route so we can attach scene and automation actions next.',
                            style: theme.textTheme.bodyLarge,
                          ),
                          const SizedBox(height: 16),
                          Wrap(
                            spacing: 10,
                            runSpacing: 10,
                            children: const <Widget>[
                              StatusPill(label: 'GLB loaded', tone: StatusTone.success),
                              StatusPill(label: 'Camera controls', tone: StatusTone.info),
                              StatusPill(label: 'Hotspots bound', tone: StatusTone.warning),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 18),
                    if (isWide)
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Expanded(flex: 3, child: _viewerCard(theme)),
                          const SizedBox(width: 18),
                          Expanded(flex: 2, child: _controlsCard(theme)),
                        ],
                      )
                    else ...<Widget>[
                      _viewerCard(theme),
                      const SizedBox(height: 18),
                      _controlsCard(theme),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _viewerCard(ThemeData theme) {
    return PanelCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text('Real-time 3D model', style: theme.textTheme.titleLarge),
              const Spacer(),
              FilledButton.tonalIcon(
                onPressed: () {
                  setState(() {
                    _yawDegrees = 35;
                    _pitchDegrees = 74;
                    _distanceMeters = 2.2;
                    _activeHotspot = 'Lighting rail';
                  });
                },
                icon: const Icon(Icons.center_focus_strong_rounded),
                label: const Text('Reset view'),
              ),
            ],
          ),
          const SizedBox(height: 16),
          ClipRRect(
            borderRadius: BorderRadius.circular(28),
            child: SizedBox(
              height: 560,
              child: Stack(
                children: <Widget>[
                  Positioned.fill(
                    child: ModelViewer(
                      key: ValueKey<String>(_cameraOrbit),
                      src: 'assets/models/danah_bed.glb',
                      alt: 'Danah Smart Bed 3D model',
                      cameraControls: true,
                      autoRotate: true,
                      loading: Loading.eager,
                      interactionPrompt: InteractionPrompt.auto,
                      cameraOrbit: _cameraOrbit,
                      minCameraOrbit: '-180deg 55deg 1.2m',
                      maxCameraOrbit: '180deg 90deg 4.0m',
                      shadowIntensity: 0.95,
                      shadowSoftness: 0.9,
                      backgroundColor: SmartBedPalette.surfaceAlt(theme.brightness),
                    ),
                  ),
                  ..._hotspots(),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _controlsCard(ThemeData theme) {
    return Column(
      children: <Widget>[
        PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('Camera orbit', style: theme.textTheme.titleLarge),
              const SizedBox(height: 12),
              Text('Yaw: ${_yawDegrees.toStringAsFixed(0)}deg', style: theme.textTheme.titleMedium),
              Slider(
                value: _yawDegrees,
                min: -180,
                max: 180,
                onChanged: (value) => setState(() => _yawDegrees = value),
              ),
              Text('Pitch: ${_pitchDegrees.toStringAsFixed(0)}deg', style: theme.textTheme.titleMedium),
              Slider(
                value: _pitchDegrees,
                min: 55,
                max: 90,
                onChanged: (value) => setState(() => _pitchDegrees = value),
              ),
              Text(
                'Distance: ${_distanceMeters.toStringAsFixed(2)}m',
                style: theme.textTheme.titleMedium,
              ),
              Slider(
                value: _distanceMeters,
                min: 1.2,
                max: 4.0,
                onChanged: (value) => setState(() => _distanceMeters = value),
              ),
            ],
          ),
        ),
        const SizedBox(height: 18),
        PanelCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('Hotspot details', style: theme.textTheme.titleLarge),
              const SizedBox(height: 12),
              StatusPill(label: _activeHotspot, tone: StatusTone.info),
              const SizedBox(height: 12),
              Text(
                _hotspotDescription(_activeHotspot),
                style: theme.textTheme.bodyLarge,
              ),
              const SizedBox(height: 16),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: _hotspotNames.map((name) {
                  return FilledButton.tonal(
                    onPressed: () => setState(() => _activeHotspot = name),
                    child: Text(name),
                  );
                }).toList(growable: false),
              ),
            ],
          ),
        ),
      ],
    );
  }

  List<Widget> _hotspots() {
    return <Widget>[
      _hotspot(
        alignment: const Alignment(-0.66, -0.52),
        label: 'Lighting rail',
        color: SmartBedPalette.accent,
      ),
      _hotspot(
        alignment: const Alignment(0.60, -0.15),
        label: 'Ambient speakers',
        color: SmartBedPalette.secondaryAccent,
      ),
      _hotspot(
        alignment: const Alignment(-0.08, 0.36),
        label: 'Prayer mode zone',
        color: SmartBedPalette.gold,
      ),
      _hotspot(
        alignment: const Alignment(0.52, 0.42),
        label: 'Partner side',
        color: SmartBedPalette.warmAccent,
      ),
    ];
  }

  Widget _hotspot({
    required Alignment alignment,
    required String label,
    required Color color,
  }) {
    final active = _activeHotspot == label;
    return Align(
      alignment: alignment,
      child: GestureDetector(
        onTap: () => setState(() => _activeHotspot = label),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          width: active ? 32 : 24,
          height: active ? 32 : 24,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color.withValues(alpha: active ? 0.95 : 0.76),
            border: Border.all(color: Colors.white.withValues(alpha: 0.72), width: 2),
            boxShadow: <BoxShadow>[
              BoxShadow(
                color: color.withValues(alpha: active ? 0.50 : 0.22),
                blurRadius: active ? 24 : 14,
                spreadRadius: active ? 2 : 0,
              ),
            ],
          ),
          child: active
              ? Icon(
                  Icons.add_rounded,
                  size: 18,
                  color: Colors.black.withValues(alpha: 0.76),
                )
              : null,
        ),
      ),
    );
  }
}

const List<String> _hotspotNames = <String>[
  'Lighting rail',
  'Ambient speakers',
  'Prayer mode zone',
  'Partner side',
];

String _hotspotDescription(String label) {
  return switch (label) {
    'Lighting rail' =>
      'Primary LED strip along the headboard. This hotspot is the first target for scene color transitions and sleep-state cues.',
    'Ambient speakers' =>
      'Audio control zone for wind-down and wake-up routines. Spotify and nature sound bindings will attach here.',
    'Prayer mode zone' =>
      'Islamic-mode scene anchor for soft warm-white transitions before prayer and focused calm lighting during prayer windows.',
    'Partner side' =>
      'Second-side profile area for partner mode controls and side-specific automation tuning.',
    _ => 'Select a hotspot to inspect the next integration layer.',
  };
}
