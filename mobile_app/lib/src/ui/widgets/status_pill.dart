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
    final brightness = Theme.of(context).brightness;
    final isDark = brightness == Brightness.dark;
    final (background, foreground) = switch (tone) {
      StatusTone.success => (
        SmartBedPalette.connected.withValues(alpha: isDark ? 0.20 : 0.14),
        isDark ? const Color(0xFFBDF5D5) : const Color(0xFF15693A),
      ),
      StatusTone.warning => (
        SmartBedPalette.warning.withValues(alpha: isDark ? 0.24 : 0.14),
        isDark ? const Color(0xFFFFE0A3) : const Color(0xFF8B5A00),
      ),
      StatusTone.info => (
        SmartBedPalette.accent.withValues(alpha: isDark ? 0.18 : 0.12),
        isDark ? const Color(0xFFB9F2FF) : const Color(0xFF0B6277),
      ),
      StatusTone.danger => (
        SmartBedPalette.danger.withValues(alpha: isDark ? 0.22 : 0.14),
        isDark ? const Color(0xFFFFC9C9) : const Color(0xFF8F1F1F),
      ),
      StatusTone.neutral => (
        SmartBedPalette.surfaceAlt(brightness).withValues(alpha: isDark ? 0.92 : 0.96),
        SmartBedPalette.body(brightness),
      ),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: foreground.withValues(alpha: 0.25)),
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

