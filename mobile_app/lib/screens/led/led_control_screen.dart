import 'dart:math' as math;
import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';
import '../../services/api_service.dart';

class LedControlScreen extends StatefulWidget {
  const LedControlScreen({super.key});

  @override
  State<LedControlScreen> createState() => _LedControlScreenState();
}

class _LedControlScreenState extends State<LedControlScreen> {
  Color _selectedColor = const Color(0xFF00D4FF);
  double _brightness = 0.8;
  bool _isSending = false;

  final List<Color> _favoriteColors = [
    const Color(0xFF00D4FF), // Cyan
    const Color(0xFF7B68EE), // Purple
    const Color(0xFFFF6B35), // Orange
    const Color(0xFFFFD700), // Gold
    const Color(0xFFFF1493), // Pink
    const Color(0xFF00FF00), // Green
  ];

  Future<void> _applyColor() async {
    setState(() => _isSending = true);
    
    final colorHex = _selectedColor.toARGB32().toRadixString(16).substring(2);
    final brightness = (_brightness * 100).toInt();
    
    await ApiService.setLighting('#$colorHex', brightness);
    
    if (mounted) {
      setState(() => _isSending = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('LED color applied!'),
          backgroundColor: AppColors.accent,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.white,
        elevation: 0,
        title: const Text(
          'LED Control',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildPreviewCard(),
            const SizedBox(height: 24),
            _buildColorWheel(),
            const SizedBox(height: 24),
            _buildBrightnessSlider(),
            const SizedBox(height: 24),
            _buildFavoriteColors(),
            const SizedBox(height: 24),
            _buildApplyButton(),
          ],
        ),
      ),
    );
  }

  Widget _buildPreviewCard() {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      width: double.infinity,
      height: 160,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: RadialGradient(
          colors: [
            _selectedColor.withValues(alpha: _brightness),
            _selectedColor.withValues(alpha: _brightness * 0.3),
            AppColors.cardBg,
          ],
        ),
        border: Border.all(
          color: _selectedColor.withValues(alpha: 0.5),
          width: 2,
        ),
        boxShadow: [
          BoxShadow(
            color: _selectedColor.withValues(alpha: _brightness * 0.6),
            blurRadius: 30,
            spreadRadius: 5,
          ),
        ],
      ),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.lightbulb_rounded,
              size: 64,
              color: Colors.white.withValues(alpha: _brightness),
            ),
            const SizedBox(height: 8),
            const Text(
              'LED Preview',
              style: TextStyle(
                color: AppColors.white,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildColorWheel() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Choose Color',
          style: TextStyle(
            color: AppColors.white,
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 12),
        Center(
          child: GestureDetector(
            onPanDown: (details) => _updateColorFromPosition(details.localPosition),
            onPanUpdate: (details) => _updateColorFromPosition(details.localPosition),
            child: Container(
              width: 280,
              height: 280,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: _selectedColor.withValues(alpha: 0.4),
                    blurRadius: 20,
                    spreadRadius: 5,
                  ),
                ],
              ),
              child: CustomPaint(
                painter: _ColorWheelPainter(),
                child: Center(
                  child: Container(
                    width: 60,
                    height: 60,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: _selectedColor,
                      border: Border.all(color: AppColors.white, width: 3),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.3),
                          blurRadius: 10,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  void _updateColorFromPosition(Offset position) {
    final center = const Offset(140, 140);
    final delta = position - center;
    final distance = delta.distance;
    
    if (distance > 140) return;
    
    final hue = (math.atan2(delta.dy, delta.dx) * 180 / math.pi + 360) % 360;
    final saturation = (distance / 140).clamp(0.0, 1.0);
    
    setState(() {
      _selectedColor = HSVColor.fromAHSV(1.0, hue, saturation, 1.0).toColor();
    });
  }

  Widget _buildBrightnessSlider() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text(
              'Brightness',
              style: TextStyle(
                color: AppColors.white,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
            Text(
              '${(_brightness * 100).toInt()}%',
              style: const TextStyle(
                color: AppColors.accent,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Container(
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(12),
            color: AppColors.cardBg,
          ),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          child: Row(
            children: [
              const Icon(Icons.brightness_low, color: AppColors.softWhite, size: 20),
              Expanded(
                child: Slider(
                  value: _brightness,
                  onChanged: (value) => setState(() => _brightness = value),
                  activeColor: _selectedColor,
                  inactiveColor: AppColors.softWhite.withValues(alpha: 0.3),
                ),
              ),
              const Icon(Icons.brightness_high, color: AppColors.softWhite, size: 20),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildFavoriteColors() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Favorite Colors',
          style: TextStyle(
            color: AppColors.white,
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 12,
          runSpacing: 12,
          children: _favoriteColors.map((color) {
            final isSelected = _selectedColor == color;
            return GestureDetector(
              onTap: () => setState(() => _selectedColor = color),
              child: Container(
                width: 50,
                height: 50,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: color,
                  border: Border.all(
                    color: isSelected ? AppColors.white : Colors.transparent,
                    width: 3,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: color.withValues(alpha: 0.5),
                      blurRadius: isSelected ? 12 : 6,
                      spreadRadius: isSelected ? 2 : 0,
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        ),
      ],
    );
  }

  Widget _buildApplyButton() {
    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        onPressed: _isSending ? null : _applyColor,
        style: FilledButton.styleFrom(
          backgroundColor: _selectedColor,
          foregroundColor: AppColors.background,
          padding: const EdgeInsets.symmetric(vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
        icon: _isSending
            ? const SizedBox(
                width: 20,
                height: 20,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: AppColors.background,
                ),
              )
            : const Icon(Icons.check_rounded, size: 24),
        label: Text(
          _isSending ? 'Applying...' : 'Apply to Bed',
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        ),
      ),
    );
  }
}

class _ColorWheelPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final radius = size.width / 2;

    for (var i = 0; i < 360; i++) {
      final hue = i.toDouble();
      final paint = Paint()
        ..shader = RadialGradient(
          colors: [
            HSVColor.fromAHSV(1.0, hue, 1.0, 1.0).toColor(),
            HSVColor.fromAHSV(1.0, hue, 0.0, 1.0).toColor(),
          ],
        ).createShader(Rect.fromCircle(center: center, radius: radius));

      final startAngle = (i - 0.5) * math.pi / 180;
      final sweepAngle = 1 * math.pi / 180;

      canvas.drawArc(
        Rect.fromCircle(center: center, radius: radius),
        startAngle,
        sweepAngle,
        true,
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
