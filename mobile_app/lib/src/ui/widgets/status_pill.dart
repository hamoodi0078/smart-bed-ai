import 'package:flutter/material.dart';

import '../theme.dart';

enum StatusTone { neutral, success, warning, info, danger }

class StatusPill extends StatelessWidget {
  const StatusPill({
    required this.label,
    super.key,
    this.tone = StatusTone.neutral,
  });

  final String label;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    final (background, foreground) = switch (tone) {
      StatusTone.success => (
        SmartBedPalette.connected.withValues(alpha: 0.24),
        const Color(0xFFB8F7CF),
      ),
      StatusTone.warning => (
        SmartBedPalette.warning.withValues(alpha: 0.25),
        const Color(0xFFFFDE9A),
      ),
      StatusTone.info => (
        SmartBedPalette.secondaryAccent.withValues(alpha: 0.24),
        const Color(0xFFBDF3FF),
      ),
      StatusTone.danger => (
        SmartBedPalette.danger.withValues(alpha: 0.25),
        const Color(0xFFFFC7C7),
      ),
      StatusTone.neutral => (
        SmartBedPalette.surfaceLight.withValues(alpha: 0.9),
        SmartBedPalette.bodyText,
      ),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: foreground.withValues(alpha: 0.3),
        ),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: foreground,
          fontSize: 12,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.1,
        ),
      ),
    );
  }
}
