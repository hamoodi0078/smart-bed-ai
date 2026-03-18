import 'package:flutter/material.dart';

import '../../services/api_service.dart';
import '../../theme/app_theme.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _selectedIndex = 0;
  bool _isLoading = true;
  Map<String, dynamic> _bedStatus = <String, dynamic>{};

  @override
  void initState() {
    super.initState();
    _loadStatus();
  }

  Future<void> _loadStatus() async {
    final data = await ApiService.getBedStatus();
    if (mounted && data['error'] != true) {
      setState(() {
        _bedStatus = data;
        _isLoading = false;
      });
    } else {
      if (mounted) {
        setState(() => _isLoading = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: Column(
          children: [
            if (_isLoading)
              const LinearProgressIndicator(
                minHeight: 2,
                color: Color(0xFF00D4FF),
                backgroundColor: Colors.transparent,
              ),
            Expanded(
              child: RefreshIndicator(
                color: const Color(0xFF00D4FF),
                onRefresh: _loadStatus,
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildTopBar(),
                      const SizedBox(height: 20),
                      _buildDanaGreetingCard(),
                      const SizedBox(height: 16),
                      _buildQuickStatsRow(),
                      const SizedBox(height: 20),
                      _buildWindDownButton(context),
                      const SizedBox(height: 20),
                      _buildIslamicSection(),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
      bottomNavigationBar: BottomNavigationBar(
        type: BottomNavigationBarType.fixed,
        backgroundColor: AppColors.cardBg,
        selectedItemColor: AppColors.accent,
        unselectedItemColor: AppColors.softWhite.withValues(alpha: 0.65),
        currentIndex: _selectedIndex,
        onTap: (index) {
          setState(() {
            _selectedIndex = index;
          });
        },
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.home_rounded), label: 'Home'),
          BottomNavigationBarItem(icon: Icon(Icons.nightlight_round), label: 'Wind-Down'),
          BottomNavigationBarItem(icon: Icon(Icons.mosque_rounded), label: 'Islamic'),
          BottomNavigationBarItem(icon: Icon(Icons.bar_chart_rounded), label: 'Report'),
        ],
      ),
    );
  }

  Widget _buildTopBar() {
    return Row(
      children: [
        Expanded(
          child: Row(
            children: const [
              Text(
                'Good Evening, Hamoud',
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
              SizedBox(width: 6),
              Icon(
                Icons.nightlight_round,
                color: AppColors.softWhite,
                size: 18,
              ),
            ],
          ),
        ),
        Container(
          decoration: BoxDecoration(
            color: AppColors.cardBg,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: AppColors.accent.withValues(alpha: 0.35)),
          ),
          child: IconButton(
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.nightlight_round, color: AppColors.softWhite),
            onPressed: () {},
            tooltip: 'Night settings',
          ),
        ),
      ],
    );
  }

  Widget _buildDanaGreetingCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0A1628), Color(0xFF243659)],
        ),
        border: Border.all(color: AppColors.accent.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: const [
              Icon(
                Icons.nightlight_round,
                color: AppColors.accent,
                size: 18,
              ),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'Peace be with you. Ready for a restful night?',
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                    height: 1.4,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          const Text(
            'Dana Guide',
            style: TextStyle(
              color: AppColors.accent,
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildQuickStatsRow() {
    final String lastNight = (_bedStatus['last_night_hours'] ?? '7.2h').toString();
    final String sleepScore = (_bedStatus['sleep_score'] ?? '82').toString();
    final String streak = (_bedStatus['streak_days'] ?? '5').toString();

    return Row(
      children: [
        Expanded(
          child: _StatCard(
            label: 'Last Night',
            value: lastNight,
            accentColor: AppColors.accent,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _StatCard(
            label: 'Sleep Score',
            value: sleepScore,
            accentColor: AppColors.purple,
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _StatCard(
            label: 'Streak',
            value: streak,
            accentColor: AppColors.orange,
            trailingIcon: Icons.local_fire_department,
          ),
        ),
      ],
    );
  }

  Widget _buildWindDownButton(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: FilledButton(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.accent,
          foregroundColor: AppColors.background,
          padding: const EdgeInsets.symmetric(vertical: 16),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        ),
        onPressed: () {
          Navigator.of(context).push(
            MaterialPageRoute<void>(builder: (_) => const WindDownScreen()),
          );
        },
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'Start Wind-Down Journey',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
            SizedBox(width: 8),
            Icon(Icons.nightlight_round, size: 18),
          ],
        ),
      ),
    );
  }

  Widget _buildIslamicSection() {
    final String nextPrayer = (_bedStatus['next_prayer'] ?? 'Isha').toString();
    final String prayerCountdown =
        (_bedStatus['next_prayer_eta'] ?? 'in 45 minutes').toString();

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(18),
        boxShadow: const [
          BoxShadow(
            color: Color(0x24FFF5E0),
            blurRadius: 20,
            spreadRadius: 1,
            offset: Offset(0, 0),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.mosque_rounded, color: AppColors.softWhite, size: 16),
              SizedBox(width: 6),
              Text(
                'Next Prayer',
                style: TextStyle(
                  color: AppColors.softWhite,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            nextPrayer,
            style: TextStyle(
              color: AppColors.white,
              fontSize: 22,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            prayerCountdown,
            style: TextStyle(
              color: AppColors.accent,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.label,
    required this.value,
    required this.accentColor,
    this.trailingIcon,
  });

  final String label;
  final String value;
  final Color accentColor;
  final IconData? trailingIcon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: AppColors.softWhite,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 6),
          Row(
            children: [
              Text(
                value,
                style: TextStyle(
                  color: accentColor,
                  fontSize: 18,
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (trailingIcon != null) ...[
                const SizedBox(width: 4),
                Icon(
                  trailingIcon,
                  size: 16,
                  color: accentColor,
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

class WindDownScreen extends StatelessWidget {
  const WindDownScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.white,
        title: const Text('Wind-Down Journey'),
      ),
      body: const Center(
        child: Text(
          'Wind-Down journey screen placeholder',
          style: TextStyle(color: AppColors.softWhite),
        ),
      ),
    );
  }
}
