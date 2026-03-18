import 'package:flutter/material.dart';

import '../theme.dart';

class PanelCard extends StatelessWidget {
  const PanelCard({
    required this.child,
    super.key,
    this.padding = const EdgeInsets.all(20),
    this.gradient,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final Gradient? gradient;

  @override
  Widget build(BuildContext context) {
    final brightness = Theme.of(context).brightness;
    final isDark = brightness == Brightness.dark;
    final borderColor = SmartBedPalette.accent.withValues(alpha: isDark ? 0.20 : 0.12);
    final shadowColor = SmartBedPalette.accent.withValues(alpha: isDark ? 0.18 : 0.08);

    return DecoratedBox(
      decoration: BoxDecoration(
        gradient:
            gradient ??
            LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: <Color>[
                SmartBedPalette.surface(brightness),
                SmartBedPalette.surfaceAlt(brightness),
              ],
            ),
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: borderColor),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: shadowColor,
            blurRadius: isDark ? 30 : 22,
            spreadRadius: -10,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(padding: padding, child: child),
    );
  }
}

