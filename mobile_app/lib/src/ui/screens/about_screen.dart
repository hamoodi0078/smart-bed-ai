import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../theme.dart';
import '../widgets/panel_card.dart';
import '../widgets/status_pill.dart';

class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  Future<void> _open(BuildContext context, String url) async {
    final launched = await launchUrl(
      Uri.parse(url),
      mode: LaunchMode.externalApplication,
    );
    if (!launched && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Unable to open link.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          onPressed: () => context.pop(),
          icon: const Icon(Icons.arrow_back_rounded),
        ),
        title: const Text('About Danah'),
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
                Text('Danah Abu Halifa', style: theme.textTheme.headlineMedium),
                const SizedBox(height: 8),
                Text(
                  'Wake Up to Intelligence',
                  style: theme.textTheme.titleLarge,
                ),
                const SizedBox(height: 10),
                Text(
                  'AI-powered smart bed companion focused on better sleep routines, guided wind-down, prayer-aware calm mode, and practical nightly automation.',
                  style: theme.textTheme.bodyLarge,
                ),
                const SizedBox(height: 14),
                const Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: <Widget>[
                    StatusPill(label: 'Built by Dana', tone: StatusTone.info),
                    StatusPill(label: 'Kuwait-ready', tone: StatusTone.success),
                    StatusPill(label: 'Version 1.0.0', tone: StatusTone.neutral),
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
                Text('Social and support', style: theme.textTheme.titleLarge),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: <Widget>[
                    FilledButton.tonalIcon(
                      onPressed: () => _open(context, 'https://instagram.com'),
                      icon: const Icon(Icons.camera_alt_outlined),
                      label: const Text('Instagram'),
                    ),
                    FilledButton.tonalIcon(
                      onPressed: () => _open(context, 'https://facebook.com'),
                      icon: const Icon(Icons.facebook_rounded),
                      label: const Text('Facebook'),
                    ),
                    FilledButton.tonalIcon(
                      onPressed: () => _open(context, 'https://tiktok.com'),
                      icon: const Icon(Icons.music_note_rounded),
                      label: const Text('TikTok'),
                    ),
                    FilledButton.tonalIcon(
                      onPressed: () => _open(context, 'https://youtube.com'),
                      icon: const Icon(Icons.ondemand_video_rounded),
                      label: const Text('YouTube'),
                    ),
                    FilledButton.tonalIcon(
                      onPressed: () => _open(context, 'https://wa.me/'),
                      icon: const Icon(Icons.chat_bubble_outline_rounded),
                      label: const Text('WhatsApp'),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                SelectableText(
                  'support@danahabuhalifa.com',
                  style: theme.textTheme.bodyMedium,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
