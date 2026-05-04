import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

/// Circular avatar that loads a remote image with caching and a fallback initial.
class CachedAvatar extends StatelessWidget {
  const CachedAvatar({
    super.key,
    this.imageUrl,
    this.initial = '?',
    this.radius = 18.0,
    this.backgroundColor = const Color(0xFF7B68EE),
  });

  final String? imageUrl;
  final String initial;
  final double radius;
  final Color backgroundColor;

  @override
  Widget build(BuildContext context) {
    final url = (imageUrl ?? '').trim();
    if (url.isEmpty) {
      return _fallback();
    }
    return CachedNetworkImage(
      imageUrl: url,
      imageBuilder: (_, imageProvider) => CircleAvatar(
        radius: radius,
        backgroundImage: imageProvider,
      ),
      placeholder: (_, __) => _fallback(),
      errorWidget: (_, __, ___) => _fallback(),
    );
  }

  Widget _fallback() {
    return CircleAvatar(
      radius: radius,
      backgroundColor: backgroundColor,
      child: Text(
        initial.isNotEmpty ? initial[0].toUpperCase() : '?',
        style: TextStyle(
          color: Colors.white,
          fontSize: radius * 0.8,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}