import 'package:flutter/material.dart';

import '../theme.dart';

class AppBackdrop extends StatelessWidget {
  const AppBackdrop({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final brightness = Theme.of(context).brightness;
    final isDark = brightness == Brightness.dark;
    final background = SmartBedPalette.scaffold(brightness);
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            background,
            SmartBedPalette.surface(brightness),
            background,
          ],
        ),
      ),
      child: Stack(
        children: <Widget>[
          _GlowBlob(
            alignment: Alignment.topLeft,
            color: SmartBedPalette.accent.withValues(alpha: isDark ? 0.18 : 0.10),
            size: 340,
            offsetX: -110,
            offsetY: -100,
          ),
          _GlowBlob(
            alignment: Alignment.topRight,
            color: SmartBedPalette.secondaryAccent.withValues(alpha: isDark ? 0.14 : 0.08),
            size: 300,
            offsetX: 100,
            offsetY: -90,
          ),
          _GlowBlob(
            alignment: Alignment.bottomRight,
            color: SmartBedPalette.warmAccent.withValues(alpha: isDark ? 0.12 : 0.07),
            size: 360,
            offsetX: 140,
            offsetY: 120,
          ),
          child,
        ],
      ),
    );
  }
}

class _GlowBlob extends StatelessWidget {
  const _GlowBlob({
    required this.alignment,
    required this.color,
    required this.size,
    required this.offsetX,
    required this.offsetY,
  });

  final Alignment alignment;
  final Color color;
  final double size;
  final double offsetX;
  final double offsetY;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: alignment,
      child: Transform.translate(
        offset: Offset(offsetX, offsetY),
        child: IgnorePointer(
          child: Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              color: color,
              shape: BoxShape.circle,
              boxShadow: <BoxShadow>[
                BoxShadow(color: color, blurRadius: 120, spreadRadius: 24),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

