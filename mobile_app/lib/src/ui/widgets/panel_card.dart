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
    final borderColor = SmartBedPalette.secondaryAccent.withValues(alpha: 0.22);
    final boxShadowColor = SmartBedPalette.accent.withValues(alpha: 0.28);
    return Container(
      decoration: BoxDecoration(
        gradient:
            gradient ??
            const LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: <Color>[
                SmartBedPalette.surfaceDark,
                SmartBedPalette.surfaceLight,
              ],
            ),
        color: gradient == null ? SmartBedPalette.surfaceDark : null,
        borderRadius: BorderRadius.circular(28),
        border: Border.all(color: borderColor),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: boxShadowColor,
            blurRadius: 34,
            spreadRadius: -10,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Padding(padding: padding, child: child),
    );
  }
}
