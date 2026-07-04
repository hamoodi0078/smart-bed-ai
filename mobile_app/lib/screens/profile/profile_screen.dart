import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../../theme/app_theme.dart';
import '../../services/api_service.dart';
import '../achievements/achievements_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  bool _isLoading = true;
  Map<String, dynamic> _userData = {};
  Map<String, dynamic> _stats = {};
  File? _localAvatar;

  @override
  void initState() {
    super.initState();
    _loadProfile();
  }

  Future<void> _pickProfileImage() async {
    final picked = await ImagePicker().pickImage(
      source: ImageSource.gallery,
      maxWidth: 512,
      maxHeight: 512,
      imageQuality: 85,
    );
    if (picked != null && mounted) {
      setState(() => _localAvatar = File(picked.path));
    }
  }

  Future<void> _loadProfile() async {
    setState(() => _isLoading = true);

    final user = await ApiService.getUserMe();
    final dashboard = await ApiService.getDashboard();

    if (mounted) {
      setState(() {
        if (user['error'] != true) {
          _userData = user;
        }
        if (dashboard['error'] != true) {
          _stats = (dashboard['weekly_insight'] as Map<String, dynamic>?) ?? {};
        }
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final String userName = (_userData['name'] ?? _userData['full_name'] ?? 'User') as String;
    final String userEmail = (_userData['email'] ?? '') as String;
    final int sleepScore = (_stats['completion_rate_pct'] as num? ?? 0).toInt();
    final int totalSessions = (_stats['wind_down_sessions'] as num? ?? 0).toInt();
    final int streakDays = (_stats['streak_days'] as num? ?? 0).toInt();

    return Scaffold(
      backgroundColor: AppColors.background,
      body: _isLoading
          ? const Center(
              child: CircularProgressIndicator(color: AppColors.accent),
            )
          : CustomScrollView(
              slivers: [
                SliverAppBar(
                  expandedHeight: 200,
                  pinned: true,
                  backgroundColor: AppColors.background,
                  flexibleSpace: FlexibleSpaceBar(
                    background: Container(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            AppColors.accent.withValues(alpha: 0.2),
                            AppColors.background,
                          ],
                        ),
                      ),
                      child: SafeArea(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            GestureDetector(
                              onTap: _pickProfileImage,
                              child: Stack(
                                children: [
                                  Container(
                                    width: 100,
                                    height: 100,
                                    decoration: BoxDecoration(
                                      shape: BoxShape.circle,
                                      gradient: const LinearGradient(
                                        colors: [AppColors.accent, AppColors.purple],
                                      ),
                                      border: Border.all(color: AppColors.white, width: 3),
                                      image: _localAvatar != null
                                          ? DecorationImage(
                                              image: FileImage(_localAvatar!),
                                              fit: BoxFit.cover,
                                            )
                                          : null,
                                    ),
                                    child: _localAvatar == null
                                        ? Center(
                                            child: Text(
                                              userName[0].toUpperCase(),
                                              style: const TextStyle(
                                                color: AppColors.white,
                                                fontSize: 42,
                                                fontWeight: FontWeight.w700,
                                              ),
                                            ),
                                          )
                                        : null,
                                  ),
                                  Positioned(
                                    bottom: 0,
                                    right: 0,
                                    child: Container(
                                      padding: const EdgeInsets.all(5),
                                      decoration: const BoxDecoration(
                                        color: AppColors.accent,
                                        shape: BoxShape.circle,
                                      ),
                                      child: const Icon(
                                        Icons.camera_alt_rounded,
                                        color: AppColors.white,
                                        size: 14,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 12),
                            Text(
                              userName,
                              style: const TextStyle(
                                color: AppColors.white,
                                fontSize: 24,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              userEmail,
                              style: TextStyle(
                                color: AppColors.softWhite.withValues(alpha: 0.8),
                                fontSize: 14,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _buildStatsGrid(
                          sleepScore: sleepScore,
                          totalSessions: totalSessions,
                          streakDays: streakDays,
                        ),
                        const SizedBox(height: 20),
                        _buildAchievementsSection(),
                        const SizedBox(height: 20),
                        _buildQuickActions(),
                        const SizedBox(height: 20),
                        _buildAccountSection(),
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }

  Widget _buildStatsGrid({
    required int sleepScore,
    required int totalSessions,
    required int streakDays,
  }) {
    return GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 3,
      childAspectRatio: 1,
      crossAxisSpacing: 12,
      mainAxisSpacing: 12,
      children: [
        _StatCard(
          icon: Icons.stars_rounded,
          value: '$sleepScore',
          label: 'Sleep Score',
          color: sleepScore > 70 ? Colors.green : AppColors.accent,
        ),
        _StatCard(
          icon: Icons.nightlight_round,
          value: '$totalSessions',
          label: 'Sessions',
          color: AppColors.purple,
        ),
        _StatCard(
          icon: Icons.local_fire_department_rounded,
          value: '$streakDays',
          label: 'Day Streak',
          color: AppColors.orange,
        ),
      ],
    );
  }

  Widget _buildAchievementsSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text(
              'Achievements',
              style: TextStyle(
                color: AppColors.white,
                fontSize: 18,
                fontWeight: FontWeight.w700,
              ),
            ),
            TextButton(
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => const AchievementsScreen(),
                  ),
                );
              },
              child: const Text('View All'),
            ),
          ],
        ),
        const SizedBox(height: 12),
        const SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              _AchievementBadge(
                icon: Icons.nightlight_round,
                color: AppColors.purple,
                isUnlocked: true,
              ),
              _AchievementBadge(
                icon: Icons.wb_sunny_rounded,
                color: AppColors.orange,
                isUnlocked: true,
              ),
              _AchievementBadge(
                icon: Icons.star_rounded,
                color: AppColors.gold,
                isUnlocked: false,
              ),
              _AchievementBadge(
                icon: Icons.chat_bubble_rounded,
                color: AppColors.accent,
                isUnlocked: false,
              ),
              _AchievementBadge(
                icon: Icons.mosque_rounded,
                color: Colors.green,
                isUnlocked: false,
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildQuickActions() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Quick Actions',
          style: TextStyle(
            color: AppColors.white,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 12),
        _ActionTile(
          icon: Icons.settings_rounded,
          title: 'Preferences',
          subtitle: 'Customize your experience',
          onTap: () {},
        ),
        _ActionTile(
          icon: Icons.notifications_rounded,
          title: 'Notifications',
          subtitle: 'Manage alerts and reminders',
          onTap: () {},
        ),
        _ActionTile(
          icon: Icons.shield_rounded,
          title: 'Privacy & Security',
          subtitle: 'Data and account protection',
          onTap: () {},
        ),
      ],
    );
  }

  Widget _buildAccountSection() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Account',
          style: TextStyle(
            color: AppColors.white,
            fontSize: 18,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 12),
        _ActionTile(
          icon: Icons.help_outline_rounded,
          title: 'Help & Support',
          subtitle: 'Get help or send feedback',
          onTap: () {},
        ),
        _ActionTile(
          icon: Icons.info_outline_rounded,
          title: 'About',
          subtitle: 'Version 1.0.0',
          onTap: () {},
        ),
        _ActionTile(
          icon: Icons.logout_rounded,
          title: 'Sign Out',
          subtitle: 'Log out of your account',
          onTap: () async {
            final navigator = Navigator.of(context);
            await ApiService.logout();
            navigator.pushReplacementNamed('/login');
          },
          isDestructive: true,
        ),
      ],
    );
  }
}

class _StatCard extends StatelessWidget {
  const _StatCard({
    required this.icon,
    required this.value,
    required this.label,
    required this.color,
  });

  final IconData icon;
  final String value;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: AppColors.cardBg,
        border: Border.all(
          color: color.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: color, size: 28),
          const SizedBox(height: 8),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 22,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.softWhite.withValues(alpha: 0.7),
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}

class _AchievementBadge extends StatelessWidget {
  const _AchievementBadge({
    required this.icon,
    required this.color,
    required this.isUnlocked,
  });

  final IconData icon;
  final Color color;
  final bool isUnlocked;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 70,
      height: 70,
      margin: const EdgeInsets.only(right: 12),
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: isUnlocked
            ? color.withValues(alpha: 0.2)
            : AppColors.softWhite.withValues(alpha: 0.05),
        border: Border.all(
          color: isUnlocked ? color : AppColors.softWhite.withValues(alpha: 0.2),
          width: 2,
        ),
      ),
      child: Icon(
        icon,
        color: isUnlocked ? color : AppColors.softWhite.withValues(alpha: 0.3),
        size: 32,
      ),
    );
  }
}

class _ActionTile extends StatelessWidget {
  const _ActionTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.isDestructive = false,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final bool isDestructive;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: isDestructive
                        ? Colors.red.withValues(alpha: 0.1)
                        : AppColors.accent.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(
                    icon,
                    color: isDestructive ? Colors.red : AppColors.accent,
                    size: 22,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          color: isDestructive ? Colors.red : AppColors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        subtitle,
                        style: TextStyle(
                          color: AppColors.softWhite.withValues(alpha: 0.6),
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(
                  Icons.chevron_right_rounded,
                  color: AppColors.softWhite.withValues(alpha: 0.4),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
