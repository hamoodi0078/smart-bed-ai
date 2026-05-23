import 'package:flutter/material.dart';
import 'package:confetti/confetti.dart';
import '../../theme/app_theme.dart';

class AchievementsScreen extends StatefulWidget {
  const AchievementsScreen({super.key});

  @override
  State<AchievementsScreen> createState() => _AchievementsScreenState();
}

class _AchievementsScreenState extends State<AchievementsScreen> {
  late ConfettiController _confettiController;
  
  final List<_Achievement> _achievements = [
    _Achievement(
      id: '1',
      title: 'First Night',
      description: 'Complete your first wind-down journey',
      icon: Icons.nightlight_round,
      color: AppColors.purple,
      isUnlocked: true,
      unlockedAt: DateTime.now().subtract(const Duration(days: 2)),
      points: 10,
    ),
    _Achievement(
      id: '2',
      title: 'Early Bird',
      description: 'Wake up before 6 AM for 7 days straight',
      icon: Icons.wb_sunny_rounded,
      color: AppColors.orange,
      isUnlocked: true,
      unlockedAt: DateTime.now().subtract(const Duration(days: 1)),
      points: 25,
    ),
    _Achievement(
      id: '3',
      title: 'Perfect Week',
      description: 'Complete all wind-down sessions for a week',
      icon: Icons.star_rounded,
      color: AppColors.gold,
      isUnlocked: false,
      progress: 5,
      maxProgress: 7,
      points: 50,
    ),
    _Achievement(
      id: '4',
      title: 'Dana\'s Friend',
      description: 'Have 50 conversations with Dana',
      icon: Icons.chat_bubble_rounded,
      color: AppColors.accent,
      isUnlocked: false,
      progress: 23,
      maxProgress: 50,
      points: 30,
    ),
    _Achievement(
      id: '5',
      title: 'Prayer Master',
      description: 'Never miss a prayer for 30 days',
      icon: Icons.mosque_rounded,
      color: Colors.green,
      isUnlocked: false,
      progress: 12,
      maxProgress: 30,
      points: 100,
    ),
    _Achievement(
      id: '6',
      title: 'Sleep Scholar',
      description: 'Maintain 85+ sleep score for a month',
      icon: Icons.school_rounded,
      color: AppColors.purple,
      isUnlocked: false,
      progress: 0,
      maxProgress: 30,
      points: 75,
    ),
  ];

  @override
  void initState() {
    super.initState();
    _confettiController = ConfettiController(
      duration: const Duration(seconds: 3),
    );
  }

  @override
  void dispose() {
    _confettiController.dispose();
    super.dispose();
  }

  void _unlockAchievement(_Achievement achievement) {
    _confettiController.play();
    
    showDialog(
      context: context,
      builder: (context) => _AchievementUnlockedDialog(
        achievement: achievement,
      ),
    );
  }

  int get _totalPoints {
    return _achievements
        .where((a) => a.isUnlocked)
        .fold(0, (sum, a) => sum + a.points);
  }

  int get _unlockedCount {
    return _achievements.where((a) => a.isUnlocked).length;
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
          'Achievements',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: Stack(
        children: [
          Column(
            children: [
              _buildStatsHeader(),
              Expanded(
                child: ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: _achievements.length,
                  itemBuilder: (context, index) {
                    return _AchievementCard(
                      achievement: _achievements[index],
                      onTap: _achievements[index].isUnlocked
                          ? null
                          : () => _unlockAchievement(_achievements[index]),
                    );
                  },
                ),
              ),
            ],
          ),
          Align(
            alignment: Alignment.topCenter,
            child: ConfettiWidget(
              confettiController: _confettiController,
              blastDirectionality: BlastDirectionality.explosive,
              particleDrag: 0.05,
              emissionFrequency: 0.05,
              numberOfParticles: 50,
              gravity: 0.2,
              colors: const [
                AppColors.accent,
                AppColors.purple,
                AppColors.orange,
                AppColors.gold,
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatsHeader() {
    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.cardBg,
            Color(0xFF0F1C35),
          ],
        ),
        border: Border.all(
          color: AppColors.accent.withValues(alpha: 0.3),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Total Points',
                  style: TextStyle(
                    color: AppColors.softWhite,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '$_totalPoints',
                  style: const TextStyle(
                    color: AppColors.gold,
                    fontSize: 32,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
          Container(
            width: 1,
            height: 40,
            color: AppColors.softWhite.withValues(alpha: 0.2),
          ),
          const SizedBox(width: 20),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Unlocked',
                  style: TextStyle(
                    color: AppColors.softWhite,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  '$_unlockedCount / ${_achievements.length}',
                  style: const TextStyle(
                    color: AppColors.accent,
                    fontSize: 32,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AchievementCard extends StatelessWidget {
  const _AchievementCard({
    required this.achievement,
    this.onTap,
  });

  final _Achievement achievement;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          color: achievement.isUnlocked
              ? AppColors.cardBg
              : AppColors.cardBg.withValues(alpha: 0.3),
          border: Border.all(
            color: achievement.isUnlocked
                ? achievement.color.withValues(alpha: 0.5)
                : AppColors.softWhite.withValues(alpha: 0.1),
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: achievement.isUnlocked
                    ? achievement.color.withValues(alpha: 0.2)
                    : AppColors.softWhite.withValues(alpha: 0.05),
              ),
              child: Icon(
                achievement.icon,
                color: achievement.isUnlocked
                    ? achievement.color
                    : AppColors.softWhite.withValues(alpha: 0.3),
                size: 28,
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          achievement.title,
                          style: TextStyle(
                            color: achievement.isUnlocked
                                ? AppColors.white
                                : AppColors.softWhite.withValues(alpha: 0.5),
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: achievement.isUnlocked
                              ? AppColors.gold.withValues(alpha: 0.2)
                              : AppColors.softWhite.withValues(alpha: 0.05),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          '+${achievement.points}',
                          style: TextStyle(
                            color: achievement.isUnlocked
                                ? AppColors.gold
                                : AppColors.softWhite.withValues(alpha: 0.3),
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    achievement.description,
                    style: TextStyle(
                      color: AppColors.softWhite.withValues(alpha: 
                        achievement.isUnlocked ? 0.8 : 0.3,
                      ),
                      fontSize: 13,
                      height: 1.3,
                    ),
                  ),
                  if (!achievement.isUnlocked && achievement.maxProgress > 0) ...[
                    const SizedBox(height: 8),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: achievement.progress / achievement.maxProgress,
                        backgroundColor: AppColors.softWhite.withValues(alpha: 0.1),
                        valueColor: AlwaysStoppedAnimation<Color>(
                          achievement.color.withValues(alpha: 0.5),
                        ),
                        minHeight: 6,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '${achievement.progress} / ${achievement.maxProgress}',
                      style: TextStyle(
                        color: AppColors.softWhite.withValues(alpha: 0.5),
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                  if (achievement.isUnlocked && achievement.unlockedAt != null) ...[
                    const SizedBox(height: 4),
                    Text(
                      'Unlocked ${_formatDate(achievement.unlockedAt!)}',
                      style: TextStyle(
                        color: achievement.color.withValues(alpha: 0.7),
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatDate(DateTime date) {
    final now = DateTime.now();
    final difference = now.difference(date);
    
    if (difference.inDays == 0) {
      return 'today';
    } else if (difference.inDays == 1) {
      return 'yesterday';
    } else if (difference.inDays < 7) {
      return '${difference.inDays} days ago';
    } else {
      return '${date.day}/${date.month}/${date.year}';
    }
  }
}

class _AchievementUnlockedDialog extends StatelessWidget {
  const _AchievementUnlockedDialog({
    required this.achievement,
  });

  final _Achievement achievement;

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(24),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              AppColors.cardBg,
              AppColors.cardBg.withValues(alpha: 0.8),
            ],
          ),
          border: Border.all(
            color: achievement.color.withValues(alpha: 0.5),
            width: 2,
          ),
          boxShadow: [
            BoxShadow(
              color: achievement.color.withValues(alpha: 0.3),
              blurRadius: 30,
              spreadRadius: 10,
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 100,
              height: 100,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: achievement.color.withValues(alpha: 0.2),
                border: Border.all(
                  color: achievement.color,
                  width: 3,
                ),
              ),
              child: Icon(
                achievement.icon,
                color: achievement.color,
                size: 48,
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Achievement Unlocked!',
              style: TextStyle(
                color: AppColors.gold,
                fontSize: 14,
                fontWeight: FontWeight.w700,
                letterSpacing: 1,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              achievement.title,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppColors.white,
                fontSize: 22,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              achievement.description,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.softWhite.withValues(alpha: 0.8),
                fontSize: 14,
                height: 1.4,
              ),
            ),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(
                horizontal: 16,
                vertical: 8,
              ),
              decoration: BoxDecoration(
                color: AppColors.gold.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: AppColors.gold,
                ),
              ),
              child: Text(
                '+${achievement.points} points',
                style: const TextStyle(
                  color: AppColors.gold,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(height: 20),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              style: FilledButton.styleFrom(
                backgroundColor: achievement.color,
                foregroundColor: AppColors.background,
                padding: const EdgeInsets.symmetric(
                  horizontal: 32,
                  vertical: 12,
                ),
              ),
              child: const Text('Awesome!'),
            ),
          ],
        ),
      ),
    );
  }
}

class _Achievement {
  const _Achievement({
    required this.id,
    required this.title,
    required this.description,
    required this.icon,
    required this.color,
    required this.isUnlocked,
    required this.points,
    this.unlockedAt,
    this.progress = 0,
    this.maxProgress = 0,
  });

  final String id;
  final String title;
  final String description;
  final IconData icon;
  final Color color;
  final bool isUnlocked;
  final DateTime? unlockedAt;
  final int progress;
  final int maxProgress;
  final int points;
}
