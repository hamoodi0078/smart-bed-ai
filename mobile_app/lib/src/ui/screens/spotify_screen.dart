import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../state/mobile_data.dart';
import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class SpotifyScreen extends ConsumerStatefulWidget {
  const SpotifyScreen({super.key});

  @override
  ConsumerState<SpotifyScreen> createState() => _SpotifyScreenState();
}

class _SpotifyScreenState extends ConsumerState<SpotifyScreen> {
  bool _busy = false;
  double _volume = 50;

  Future<void> _refresh() async {
    ref.invalidate(spotifyStatusProvider);
    ref.invalidate(spotifyPlaybackStatusProvider);
    await Future.wait<void>(<Future<void>>[
      ref.read(spotifyStatusProvider.future).then((_) {}),
      ref.read(spotifyPlaybackStatusProvider.future).then((_) {}),
    ]);
  }

  Future<void> _connect() async {
    String authUrl = '';
    try {
      authUrl = await ref.read(smartBedRepositoryProvider).spotifyAuthUrl();
    } on ApiException catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.message)),
      );
      return;
    }
    if (authUrl.isEmpty) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Spotify auth URL is unavailable.')),
      );
      return;
    }
    final uri = Uri.parse(authUrl);
    final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!mounted) {
      return;
    }
    if (!launched) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Unable to open Spotify connect flow.')),
      );
    }
  }

  Future<void> _disconnect() async {
    setState(() {
      _busy = true;
    });
    try {
      await ref.read(smartBedRepositoryProvider).disconnectSpotify();
      if (!mounted) {
        return;
      }
      await _refresh();
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Spotify disconnected.')),
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

  Future<void> _playback(String action) async {
    setState(() {
      _busy = true;
    });
    try {
      final message = await ref
          .read(smartBedRepositoryProvider)
          .spotifyPlaybackAction(
            action: action,
            volumePercent: _volume.round(),
          );
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
    final connectionAsync = ref.watch(spotifyStatusProvider);
    final playbackAsync = ref.watch(spotifyPlaybackStatusProvider);

    final connection = connectionAsync.valueOrNull;
    final playback = playbackAsync.valueOrNull;
    final error = connectionAsync.error ?? playbackAsync.error;

    final connected = connection?.connected ?? playback?.connected ?? false;
    final playing = playback?.isPlaying ?? false;

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        title: const Text('Spotify'),
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
                Text('Music control', style: theme.textTheme.headlineMedium),
                const SizedBox(height: 8),
                Text(
                  'Control playback, volume, and bedtime audio directly from the active mobile track.',
                  style: theme.textTheme.bodyLarge,
                ),
                const SizedBox(height: 14),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: <Widget>[
                    StatusPill(
                      label: connected ? 'Connected' : 'Not connected',
                      tone: connected ? StatusTone.success : StatusTone.warning,
                    ),
                    StatusPill(
                      label: playing ? 'Playing' : 'Paused',
                      tone: playing ? StatusTone.info : StatusTone.neutral,
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
                Text('Account', style: theme.textTheme.titleLarge),
                const SizedBox(height: 10),
                if (error != null && connection == null && playback == null)
                  Text(
                    error is ApiException ? error.message : 'Unable to load Spotify state.',
                    style: theme.textTheme.bodyMedium,
                  )
                else if (!connected)
                  Text(
                    'Connect Spotify first. If browser auth redirects to login, sign in with the same Danah account and retry.',
                    style: theme.textTheme.bodyMedium,
                  )
                else
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        connection?.spotifyEmail.isNotEmpty == true
                            ? connection!.spotifyEmail
                            : 'Spotify user connected',
                        style: theme.textTheme.titleMedium,
                      ),
                      if (connection?.expiresAt.isNotEmpty == true) ...<Widget>[
                        const SizedBox(height: 4),
                        Text(
                          'Token expires: ${connection!.expiresAt}',
                          style: theme.textTheme.bodySmall,
                        ),
                      ],
                    ],
                  ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: <Widget>[
                    FilledButton.icon(
                      onPressed: _busy ? null : _connect,
                      icon: const Icon(Icons.link_rounded),
                      label: const Text('Connect'),
                    ),
                    OutlinedButton.icon(
                      onPressed: _busy || !connected ? null : _disconnect,
                      icon: const Icon(Icons.link_off_rounded),
                      label: const Text('Disconnect'),
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
                Text('Playback', style: theme.textTheme.titleLarge),
                const SizedBox(height: 10),
                Text(
                  playback?.trackName.isNotEmpty == true
                      ? '${playback!.trackName} - ${playback.artist}'
                      : 'No active track',
                  style: theme.textTheme.bodyLarge,
                ),
                if (playback?.deviceName.isNotEmpty == true) ...<Widget>[
                  const SizedBox(height: 6),
                  Text(
                    'Device: ${playback!.deviceName}',
                    style: theme.textTheme.bodySmall,
                  ),
                ],
                const SizedBox(height: 14),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: <Widget>[
                    FilledButton.tonalIcon(
                      onPressed: _busy || !connected ? null : () => _playback('previous'),
                      icon: const Icon(Icons.skip_previous_rounded),
                      label: const Text('Prev'),
                    ),
                    FilledButton.tonalIcon(
                      onPressed: _busy || !connected
                          ? null
                          : () => _playback(playing ? 'pause' : 'play'),
                      icon: Icon(
                        playing
                            ? Icons.pause_circle_outline_rounded
                            : Icons.play_circle_outline_rounded,
                      ),
                      label: Text(playing ? 'Pause' : 'Play'),
                    ),
                    FilledButton.tonalIcon(
                      onPressed: _busy || !connected ? null : () => _playback('next'),
                      icon: const Icon(Icons.skip_next_rounded),
                      label: const Text('Next'),
                    ),
                  ],
                ),
                const SizedBox(height: 18),
                Row(
                  children: <Widget>[
                    Expanded(
                      child: Text(
                        'Volume: ${_volume.round()}%',
                        style: theme.textTheme.titleMedium,
                      ),
                    ),
                    FilledButton.tonal(
                      onPressed: _busy || !connected
                          ? null
                          : () => _playback('set_volume'),
                      child: const Text('Apply'),
                    ),
                  ],
                ),
                Slider(
                  value: _volume,
                  min: 0,
                  max: 100,
                  divisions: 20,
                  onChanged: (value) {
                    setState(() {
                      _volume = value;
                    });
                  },
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

