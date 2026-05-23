import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../services/api_service.dart';
import '../theme/app_theme.dart';
import 'glass_card.dart';

// ── Provider ─────────────────────────────────────────────────────────────────

final liveSensorProvider =
    StreamProvider.autoDispose<Map<String, dynamic>>((ref) async* {
  while (true) {
    final result = await ApiService.getLiveSensors();
    yield result;
    await Future<void>.delayed(const Duration(seconds: 5));
  }
});

// ── Widget ───────────────────────────────────────────────────────────────────

class LiveSensorCard extends ConsumerWidget {
  const LiveSensorCard({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sensorAsync = ref.watch(liveSensorProvider);

    return GlassCard(
      borderRadius: 18,
      padding: const EdgeInsets.all(14),
      border: Border.all(color: AppColors.accent.withValues(alpha: 0.3)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: AppColors.accent.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.sensors_rounded,
                    color: AppColors.accent, size: 16),
              ),
              const SizedBox(width: 8),
              const Text(
                'Live Sensors',
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              sensorAsync.when(
                data: (_) => _StatusDot(color: Colors.green, label: 'Live'),
                loading: () =>
                    _StatusDot(color: AppColors.orange, label: 'Loading'),
                error: (_, __) =>
                    _StatusDot(color: Colors.red, label: 'Offline'),
              ),
            ],
          ),
          const SizedBox(height: 12),
          sensorAsync.when(
            data: (data) => _SensorGrid(data: data),
            loading: () => const _SensorGrid(data: {}),
            error: (_, __) => const _SensorGrid(data: {}),
          ),
        ],
      ),
    );
  }
}

// ── Status dot ───────────────────────────────────────────────────────────────

class _StatusDot extends StatelessWidget {
  const _StatusDot({required this.color, required this.label});

  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
            color: color,
            shape: BoxShape.circle,
            boxShadow: [
              BoxShadow(
                  color: color.withValues(alpha: 0.5),
                  blurRadius: 4,
                  spreadRadius: 1),
            ],
          ),
        ),
        const SizedBox(width: 5),
        Text(
          label,
          style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w600),
        ),
      ],
    );
  }
}

// ── Sensor grid ──────────────────────────────────────────────────────────────

class _SensorGrid extends StatelessWidget {
  const _SensorGrid({required this.data});

  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _SensorTile(
            icon: Icons.thermostat_rounded,
            label: 'Temp',
            value: _fmt(data['temperature_c'], '°C'),
            color: AppColors.orange,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _SensorTile(
            icon: Icons.water_drop_rounded,
            label: 'Humidity',
            value: _fmt(data['humidity_pct'], '%'),
            color: AppColors.accent,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _SensorTile(
            icon: Icons.favorite_rounded,
            label: 'Heart',
            value: _fmt(data['heart_rate_bpm'], ' bpm'),
            color: Colors.redAccent,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: _SensorTile(
            icon: Icons.bloodtype_rounded,
            label: 'SpO₂',
            value: _fmt(data['spo2_pct'], '%'),
            color: AppColors.purple,
          ),
        ),
      ],
    );
  }

  static String _fmt(dynamic value, String suffix) {
    if (value == null) return '--';
    if (value is num) {
      return value == value.toInt()
          ? '${value.toInt()}$suffix'
          : '${value.toStringAsFixed(1)}$suffix';
    }
    return '$value$suffix';
  }
}

// ── Individual sensor tile ───────────────────────────────────────────────────

class _SensorTile extends StatelessWidget {
  const _SensorTile({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  final IconData icon;
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.2)),
      ),
      child: Column(
        children: [
          Icon(icon, color: color, size: 18),
          const SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(
              color: AppColors.softWhite.withValues(alpha: 0.7),
              fontSize: 10,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
