import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../src/state/mobile_data.dart';
import '../../theme/app_theme.dart';

class PartnerModeScreen extends ConsumerStatefulWidget {
  const PartnerModeScreen({super.key});

  @override
  ConsumerState<PartnerModeScreen> createState() => _PartnerModeScreenState();
}

class _PartnerModeScreenState extends ConsumerState<PartnerModeScreen> {
  bool _partnerLinked = false;
  String _activeUser = 'You';
  String _partnerName = '';
  Map<String, dynamic>? _comparison;
  bool _loadingComparison = false;
  final TextEditingController _partnerController = TextEditingController();

  static const List<_PresetData> _presets = [
    _PresetData(
      icon: Icons.nightlight,
      title: 'Partner Quiet',
      subtitle: 'Minimal light, silent alarms, no disturbance',
    ),
    _PresetData(
      icon: Icons.balance,
      title: 'Balanced Mode',
      subtitle: 'Equal settings for both sides',
    ),
    _PresetData(
      icon: Icons.favorite,
      title: 'Couple Wind-Down',
      subtitle: 'Synchronized wind-down routine for both',
    ),
  ];

  @override
  void dispose() {
    _partnerController.dispose();
    super.dispose();
  }

  void _linkPartner() {
    final String enteredName = _partnerController.text.trim();
    if (enteredName.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Please enter your partner's name.")),
      );
      return;
    }

    setState(() {
      _partnerLinked = true;
      _partnerName = enteredName;
      _activeUser = 'You';
    });
    FocusScope.of(context).unfocus();
    _loadComparison();
  }

  Future<void> _loadComparison() async {
    setState(() => _loadingComparison = true);
    try {
      final data =
          await ref.read(smartBedRepositoryProvider).loadPartnerComparison();
      if (mounted) setState(() => _comparison = data);
    } catch (_) {
      // Comparison needs real sleep history on both sides; absence is not an
      // error — the banner falls back to the linked-only message.
      if (mounted) setState(() => _comparison = null);
    } finally {
      if (mounted) setState(() => _loadingComparison = false);
    }
  }

  void _activatePreset(String presetName) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('$presetName activated for both profiles! 🌙')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildTopBar(),
              const SizedBox(height: 18),
              _buildActiveProfileSection(),
              const SizedBox(height: 14),
              if (!_partnerLinked) ...[
                _buildLinkPartnerSection(),
                const SizedBox(height: 14),
              ],
              _buildSharedPresetsSection(),
              if (_partnerLinked) ...[
                const SizedBox(height: 14),
                _buildLinkedSuccessBanner(),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTopBar() {
    return Row(
      children: [
        IconButton(
          onPressed: () => Navigator.of(context).maybePop(),
          icon: const Icon(Icons.arrow_back_ios_new_rounded),
          color: AppColors.white,
          tooltip: 'Back',
        ),
        const Expanded(
          child: Text(
            'Partner Mode 👫',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.white,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(width: 48),
      ],
    );
  }

  Widget _buildActiveProfileSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Active Profile',
          style: TextStyle(
            color: Color(0xFF9CA6BF),
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
        ),
        const SizedBox(height: 10),
        Row(
          children: [
            Expanded(
              child: _buildProfileCard(
                title: 'You',
                icon: Icons.person,
                isActive: _activeUser == 'You',
                isLinked: true,
                onTap: () {
                  setState(() {
                    _activeUser = 'You';
                  });
                },
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _buildProfileCard(
                title: _partnerLinked ? _partnerName : '+ Add Partner',
                icon: _partnerLinked ? Icons.person : Icons.person_add,
                isActive: _partnerLinked && _activeUser == _partnerName,
                isLinked: _partnerLinked,
                onTap: () {
                  if (!_partnerLinked) {
                    return;
                  }
                  setState(() {
                    _activeUser = _partnerName;
                  });
                },
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildProfileCard({
    required String title,
    required IconData icon,
    required bool isActive,
    required bool isLinked,
    required VoidCallback onTap,
  }) {
    final Color borderColor = isLinked
        ? (isActive ? AppColors.accent : AppColors.softWhite.withValues(alpha: 0.2))
        : const Color(0xFF6F7993);
    final Color iconColor = isLinked
        ? (isActive ? AppColors.accent : AppColors.softWhite)
        : const Color(0xFF9AA4BF);

    if (!isLinked) {
      return InkWell(
        borderRadius: BorderRadius.circular(14),
        onTap: onTap,
        child: CustomPaint(
          painter: _DashedBorderPainter(
            color: borderColor,
            radius: 14,
            dashLength: 6,
            dashGap: 4,
          ),
          child: Container(
            height: 86,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
            alignment: Alignment.center,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Icon(icon, color: iconColor, size: 24),
                const SizedBox(height: 6),
                Text(
                  title,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: Color(0xFFB2BED8),
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: onTap,
      child: Container(
        height: 86,
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        decoration: BoxDecoration(
          color: AppColors.cardBg,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: borderColor, width: isActive ? 1.4 : 1),
        ),
        alignment: Alignment.center,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: iconColor, size: 24),
            const SizedBox(height: 6),
            Text(
              title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppColors.white,
                fontSize: 14,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLinkPartnerSection() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            "Connect Your Partner's Bed Side",
            style: TextStyle(
              color: AppColors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Each side of the bed can have its own profile, preferences, and Dana personality',
            style: TextStyle(
              color: Color(0xFF9CA6BF),
              fontSize: 13,
              height: 1.45,
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _partnerController,
            style: const TextStyle(color: AppColors.white, fontSize: 14),
            decoration: InputDecoration(
              hintText: "Partner's name",
              hintStyle: TextStyle(
                color: AppColors.softWhite.withValues(alpha: 0.6),
              ),
              filled: true,
              fillColor: const Color(0xFF121E34),
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 12,
                vertical: 12,
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(
                  color: AppColors.accent,
                  width: 1.1,
                ),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: const BorderSide(
                  color: AppColors.accent,
                  width: 1.4,
                ),
              ),
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _linkPartner,
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.accent,
                foregroundColor: AppColors.background,
                padding: const EdgeInsets.symmetric(vertical: 14),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              child: const Text(
                'Link Partner 🔗',
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSharedPresetsSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Shared Sleep Presets',
          style: TextStyle(
            color: AppColors.white,
            fontSize: 16,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 10),
        ..._presets.map((preset) {
          return Container(
            width: double.infinity,
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.cardBg,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(
                color: AppColors.softWhite.withValues(alpha: 0.1),
                width: 1,
              ),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  preset.icon,
                  color: AppColors.softWhite,
                  size: 22,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        preset.title,
                        style: const TextStyle(
                          color: AppColors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        preset.subtitle,
                        style: const TextStyle(
                          color: Color(0xFF9CA6BF),
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                SizedBox(
                  height: 30,
                  child: FilledButton(
                    onPressed: () => _activatePreset(preset.title),
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.accent,
                      foregroundColor: AppColors.background,
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                    ),
                    child: const Text(
                      'Activate',
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );
        }),
      ],
    );
  }

  Widget _buildLinkedSuccessBanner() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF1B3A2A),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: const Color(0xFF4CAF50).withValues(alpha: 0.4),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 1),
            child: Icon(
              Icons.check_circle,
              color: Color(0xFF4CAF50),
              size: 20,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '$_partnerName is linked to your bed! You can now switch profiles using the cards above.',
                  style: const TextStyle(
                    color: AppColors.white,
                    fontSize: 13,
                    height: 1.4,
                  ),
                ),
                if (_loadingComparison) ...[
                  const SizedBox(height: 8),
                  const Text(
                    'Loading shared sleep stats…',
                    style: TextStyle(color: AppColors.softWhite, fontSize: 12),
                  ),
                ] else if (_comparison != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    'Combined sleep score (last ${_comparison!['period_days'] ?? 7}d): '
                    '${_comparison!['combined_avg_score'] ?? '—'}'
                    '${_comparison!['both_met_goal'] == true ? '  •  both on target 🎯' : ''}',
                    style: const TextStyle(
                      color: Color(0xFF4CAF50),
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _PresetData {
  const _PresetData({
    required this.icon,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final String title;
  final String subtitle;
}

class _DashedBorderPainter extends CustomPainter {
  _DashedBorderPainter({
    required this.color,
    required this.radius,
    required this.dashLength,
    required this.dashGap,
  });

  final Color color;
  final double radius;
  final double dashLength;
  final double dashGap;

  @override
  void paint(Canvas canvas, Size size) {
    final Paint paint = Paint()
      ..color = color
      ..strokeWidth = 1.3
      ..style = PaintingStyle.stroke;
    final Path original = Path()
      ..addRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(0.65, 0.65, size.width - 1.3, size.height - 1.3),
          Radius.circular(radius),
        ),
      );
    final Path dashed = Path();
    for (final metric in original.computeMetrics()) {
      double distance = 0;
      while (distance < metric.length) {
        final double next = math.min(distance + dashLength, metric.length);
        dashed.addPath(metric.extractPath(distance, next), Offset.zero);
        distance += dashLength + dashGap;
      }
    }
    canvas.drawPath(dashed, paint);
  }

  @override
  bool shouldRepaint(covariant _DashedBorderPainter oldDelegate) {
    return oldDelegate.color != color ||
        oldDelegate.radius != radius ||
        oldDelegate.dashLength != dashLength ||
        oldDelegate.dashGap != dashGap;
  }
}
