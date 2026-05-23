import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';

/// Reusable shimmer skeleton components.
///
/// Usage:
///   ShimmerLoader.card()          — generic card placeholder
///   ShimmerLoader.listItem()      — avatar + two-line row
///   ShimmerLoader.circle(size: 160) — score/avatar circle
///   ShimmerLoader.textLine()      — single text line
///   ShimmerLoader.homeSkeleton()  — full HomeScreen skeleton
///   ShimmerLoader.islamicSkeleton() — full IslamicScreen skeleton
class ShimmerLoader extends StatelessWidget {
  const ShimmerLoader({super.key, required this.child});

  final Widget child;

  static const _baseColor = Color(0xFF1E2C44);
  static const _highlightColor = Color(0xFF2C3E5C);

  @override
  Widget build(BuildContext context) {
    return Shimmer.fromColors(
      baseColor: _baseColor,
      highlightColor: _highlightColor,
      child: child,
    );
  }

  // ─── Primitives ───────────────────────────────────────────────────────────

  static Widget _box({
    double? width,
    double height = 16,
    double radius = 8,
  }) {
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(radius),
      ),
    );
  }

  // ─── Public factories ─────────────────────────────────────────────────────

  /// Single rounded rectangle placeholder (generic card).
  static Widget card({double height = 90, double radius = 16}) {
    return ShimmerLoader(
      child: _box(width: double.infinity, height: height, radius: radius),
    );
  }

  /// A single text-line placeholder.
  static Widget textLine({double? width, double height = 14}) {
    return ShimmerLoader(
      child: _box(width: width, height: height, radius: 6),
    );
  }

  /// A circular placeholder (e.g. score circle, avatar).
  static Widget circle({double size = 48}) {
    return ShimmerLoader(
      child: Container(
        width: size,
        height: size,
        decoration: const BoxDecoration(
          color: Colors.white,
          shape: BoxShape.circle,
        ),
      ),
    );
  }

  /// A list-item row: circle avatar + two text lines.
  static Widget listItem() {
    return ShimmerLoader(
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: const BoxDecoration(
              color: Colors.white,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _box(width: double.infinity, height: 14),
                const SizedBox(height: 6),
                _box(width: 140, height: 12),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Full HomeScreen skeleton: greeting, score circle, stat cards, grid.
  static Widget homeSkeleton() {
    return ShimmerLoader(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Top bar
            Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _box(width: 200, height: 18),
                      const SizedBox(height: 6),
                      _box(width: 100, height: 12),
                    ],
                  ),
                ),
                Container(
                  width: 40,
                  height: 40,
                  decoration: const BoxDecoration(
                    color: Colors.white,
                    shape: BoxShape.circle,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 20),
            // Greeting card
            _box(width: double.infinity, height: 82, radius: 20),
            const SizedBox(height: 16),
            // Score circle
            Center(
              child: Container(
                width: 160,
                height: 160,
                decoration: const BoxDecoration(
                  color: Colors.white,
                  shape: BoxShape.circle,
                ),
              ),
            ),
            const SizedBox(height: 16),
            // Stat row
            Row(
              children: [
                Expanded(child: _box(height: 72, radius: 14)),
                const SizedBox(width: 10),
                Expanded(child: _box(height: 72, radius: 14)),
                const SizedBox(width: 10),
                Expanded(child: _box(height: 72, radius: 14)),
              ],
            ),
            const SizedBox(height: 16),
            // Actions grid (2×3)
            GridView.count(
              crossAxisCount: 2,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              mainAxisSpacing: 12,
              crossAxisSpacing: 12,
              childAspectRatio: 1.5,
              children: List.generate(
                6,
                (_) => _box(height: double.infinity, radius: 16),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Full IslamicScreen skeleton: prayer times card + next prayer + hadith.
  static Widget islamicSkeleton() {
    return ShimmerLoader(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Top bar
            Row(
              children: [
                _box(width: 32, height: 32, radius: 8),
                const SizedBox(width: 12),
                Expanded(child: _box(height: 20)),
                const SizedBox(width: 12),
                _box(width: 56, height: 32, radius: 20),
              ],
            ),
            const SizedBox(height: 14),
            // Prayer times card
            _box(width: double.infinity, height: 260, radius: 18),
            const SizedBox(height: 14),
            // Next prayer card
            _box(width: double.infinity, height: 120, radius: 18),
            const SizedBox(height: 14),
            // Hadith card
            _box(width: double.infinity, height: 110, radius: 18),
            const SizedBox(height: 14),
            // Hijri date
            _box(width: double.infinity, height: 56, radius: 14),
          ],
        ),
      ),
    );
  }

  /// Generic list of N card placeholders (e.g. for alarm/scene lists).
  static Widget cardList({int count = 4, double cardHeight = 76}) {
    return ShimmerLoader(
      child: Column(
        children: List.generate(
          count,
          (i) => Padding(
            padding: EdgeInsets.only(bottom: i < count - 1 ? 10 : 0),
            child: _box(
                width: double.infinity,
                height: cardHeight,
                radius: 14),
          ),
        ),
      ),
    );
  }
}
