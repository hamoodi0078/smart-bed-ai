import 'package:flutter/material.dart';

import '../theme.dart';

class AppBackdrop extends StatelessWidget {
  const AppBackdrop({required this.child, super.key});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            SmartBedPalette.background,
            SmartBedPalette.surfaceDark,
            SmartBedPalette.background,
          ],
        ),
      ),
      child: Stack(
        children: <Widget>[
          const _GlowBlob(
            alignment: Alignment.topLeft,
            color: Color(0x664F46E5),
            size: 320,
            offsetX: -110,
            offsetY: -90,
          ),
          const _GlowBlob(
            alignment: Alignment.bottomRight,
            color: Color(0x5522D3EE),
            size: 340,
            offsetX: 120,
            offsetY: 120,
          ),
          const _GlowBlob(
            alignment: Alignment.centerLeft,
            color: Color(0x334F46E5),
            size: 260,
            offsetX: -140,
            offsetY: 70,
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
                BoxShadow(color: color, blurRadius: 120, spreadRadius: 26),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
