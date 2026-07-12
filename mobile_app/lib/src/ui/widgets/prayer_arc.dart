import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../core/models.dart';
import '../theme.dart';

/// The Prayer Arc — the day rendered as a sky dome.
///
/// Five prayer marks sit on an arc at their *actual* times; the arc's
/// gradient sweeps the window hues (Fajr indigo → Dhuhr light → Asr gold →
/// Maghrib ember → Isha violet). Passed prayers dim, the next one glows,
/// and a small marker shows where "now" lives on today's arc.
///
/// Draws itself in on first build (600ms) unless the platform asks for
/// reduced motion, in which case it renders complete and still.
class PrayerArc extends StatelessWidget {
  const PrayerArc({
    super.key,
    required this.prayers,
    required this.nextPrayer,
    this.height = 150,
  });

  /// Prayer name → "HH:MM" (24h) as served by the overview endpoint.
  final Map<String, String> prayers;
  final PrayerCountdown nextPrayer;
  final double height;

  @override
  Widget build(BuildContext context) {
    final stops = _PrayerStop.fromTimes(prayers);
    if (stops.length < 2) {
      return const SizedBox.shrink();
    }
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final now = DateTime.now();

    return TweenAnimationBuilder<double>(
      tween: Tween<double>(begin: reduceMotion ? 1 : 0, end: 1),
      duration: reduceMotion ? Duration.zero : MotionTokens.slow,
      curve: Curves.easeOutCubic,
      builder: (context, progress, _) {
        return SizedBox(
          height: height,
          width: double.infinity,
          child: CustomPaint(
            painter: _PrayerArcPainter(
              stops: stops,
              nextPrayerName: nextPrayer.name,
              nowMinutes: now.hour * 60 + now.minute,
              progress: progress,
              labelColor:
                  SmartBedPalette.body(Theme.of(context).brightness),
            ),
          ),
        );
      },
    );
  }
}

class _PrayerStop {
  const _PrayerStop(this.name, this.minutes, this.color);

  final String name;
  final int minutes;
  final Color color;

  /// Parse the overview's prayer map into ordered stops. Tolerates missing
  /// prayers and both "HH:MM" and "hh:mm AM/PM" formats.
  static List<_PrayerStop> fromTimes(Map<String, String> prayers) {
    final stops = <_PrayerStop>[];
    for (final name in PrayerWindowPalette.canonicalOrder) {
      final raw = prayers.entries
          .where((e) => e.key.trim().toLowerCase() == name.toLowerCase())
          .map((e) => e.value)
          .firstOrNull;
      final minutes = _parseMinutes(raw);
      if (minutes != null) {
        stops.add(_PrayerStop(name, minutes, PrayerWindowPalette.forName(name)));
      }
    }
    stops.sort((a, b) => a.minutes.compareTo(b.minutes));
    return stops;
  }

  static int? _parseMinutes(String? raw) {
    if (raw == null) return null;
    final text = raw.trim();
    final match = RegExp(r'^(\d{1,2}):(\d{2})').firstMatch(text);
    if (match == null) return null;
    var hour = int.parse(match.group(1)!);
    final minute = int.parse(match.group(2)!);
    final upper = text.toUpperCase();
    if (upper.contains('PM') && hour < 12) hour += 12;
    if (upper.contains('AM') && hour == 12) hour = 0;
    if (hour > 23 || minute > 59) return null;
    return hour * 60 + minute;
  }
}

class _PrayerArcPainter extends CustomPainter {
  _PrayerArcPainter({
    required this.stops,
    required this.nextPrayerName,
    required this.nowMinutes,
    required this.progress,
    required this.labelColor,
  });

  final List<_PrayerStop> stops;
  final String nextPrayerName;
  final int nowMinutes;
  final double progress;
  final Color labelColor;

  static const int _segments = 72;
  static const double _labelZone = 26; // reserved for names under the arc

  /// Fraction [0..1] of a time within the padded Fajr→Isha span.
  double _fractionOf(int minutes) {
    final start = stops.first.minutes - 40;
    final end = stops.last.minutes + 40;
    if (end <= start) return 0;
    return ((minutes - start) / (end - start)).clamp(0.0, 1.0);
  }

  /// Point on the dome for fraction t. The dome is an ellipse arc spanning
  /// the width, flattened so labels and glow have breathing room.
  Offset _pointAt(double t, Size size) {
    final rx = size.width / 2 - 18;
    final ry = size.height - _labelZone - 26;
    final cx = size.width / 2;
    final cy = size.height - _labelZone;
    final angle = math.pi * (1 - t);
    return Offset(cx + rx * math.cos(angle), cy - ry * math.sin(angle));
  }

  Color _colorAt(double t) {
    if (stops.length == 1) return stops.first.color;
    final fractions = stops.map((s) => _fractionOf(s.minutes)).toList();
    if (t <= fractions.first) return stops.first.color;
    if (t >= fractions.last) return stops.last.color;
    for (var i = 0; i < fractions.length - 1; i++) {
      if (t >= fractions[i] && t <= fractions[i + 1]) {
        final span = fractions[i + 1] - fractions[i];
        final local = span == 0 ? 0.0 : (t - fractions[i]) / span;
        return Color.lerp(stops[i].color, stops[i + 1].color, local)!;
      }
    }
    return stops.last.color;
  }

  @override
  void paint(Canvas canvas, Size size) {
    // 1. The arc itself: short segments, each lerped along the window hues,
    //    revealed left-to-right by [progress].
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.5
      ..strokeCap = StrokeCap.round;
    final visibleSegments = (_segments * progress).floor();
    for (var i = 0; i < visibleSegments; i++) {
      final t0 = i / _segments;
      final t1 = (i + 1) / _segments;
      paint.color = _colorAt((t0 + t1) / 2).withValues(alpha: 0.85);
      canvas.drawLine(_pointAt(t0, size), _pointAt(t1, size), paint);
    }

    // 2. Prayer marks + labels, appearing as the sweep passes them.
    final textStyle = TextStyle(
      color: labelColor,
      fontSize: 10.5,
      fontWeight: FontWeight.w600,
      letterSpacing: 0.2,
    );
    for (final stop in stops) {
      final t = _fractionOf(stop.minutes);
      if (t > progress) continue;
      final p = _pointAt(t, size);
      final passed = stop.minutes < nowMinutes;
      final isNext =
          stop.name.toLowerCase() == nextPrayerName.trim().toLowerCase();

      if (isNext) {
        // Halo for the next prayer.
        canvas.drawCircle(
          p,
          11,
          Paint()
            ..color = stop.color.withValues(alpha: 0.35)
            ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6),
        );
      }
      canvas.drawCircle(
        p,
        isNext ? 5.5 : 4,
        Paint()
          ..color = passed && !isNext
              ? stop.color.withValues(alpha: 0.35)
              : stop.color,
      );

      final painter = TextPainter(
        text: TextSpan(
          text: stop.name,
          style: isNext
              ? textStyle.copyWith(
                  color: stop.color, fontWeight: FontWeight.w800)
              : textStyle,
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      // Edge labels hug inward so they never clip.
      final dx = (p.dx - painter.width / 2)
          .clamp(2.0, size.width - painter.width - 2);
      painter.paint(canvas, Offset(dx, size.height - _labelZone + 8));
    }

    // 3. "Now" marker — a soft white point on today's position.
    final tNow = _fractionOf(nowMinutes);
    if (tNow <= progress) {
      final p = _pointAt(tNow, size);
      canvas.drawCircle(
        p,
        8,
        Paint()
          ..color = Colors.white.withValues(alpha: 0.30)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 5),
      );
      canvas.drawCircle(p, 3, Paint()..color = Colors.white);
    }
  }

  @override
  bool shouldRepaint(_PrayerArcPainter oldDelegate) =>
      oldDelegate.progress != progress ||
      oldDelegate.nowMinutes != nowMinutes ||
      oldDelegate.nextPrayerName != nextPrayerName ||
      oldDelegate.stops != stops;
}
