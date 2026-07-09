import 'package:flutter/material.dart';
import 'package:confetti/confetti.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../theme/app_theme.dart';
import '../../src/state/mobile_data.dart';

/// Maps a backend achievement category to an icon + accent colour so the
/// visual language survives even though the engine only returns a category.
class _CategoryStyle {
  const _CategoryStyle(this.icon, this.color);
  final IconData icon;
  final Color color;
}

const Map<String, _CategoryStyle> _categoryStyles = {
  'sleep': _CategoryStyle(Icons.nightlight_round, AppColors.purple),
  'wake': _CategoryStyle(Icons.wb_sunny_rounded, AppColors.orange),
  'streak': _CategoryStyle(Icons.local_fire_department_rounded, AppColors.orange),
  'dana': _CategoryStyle(Icons.chat_bubble_rounded, AppColors.accent),
  'chat': _CategoryStyle(Icons.chat_bubble_rounded, AppColors.accent),
  'islamic': _CategoryStyle(Icons.mosque_rounded, Colors.green),
  'prayer': _CategoryStyle(Icons.mosque_rounded, Colors.green),
  'health': _CategoryStyle(Icons.favorite_rounded, Colors.pinkAccent),
  'milestone': _CategoryStyle(Icons.star_rounded, AppColors.gold),
};

_CategoryStyle _styleFor(String category) =>
    _categoryStyles[category.toLowerCase()] ??
    const _CategoryStyle(Icons.emoji_events_rounded, AppColors.gold);

/// Fallback list shown only when the backend is unreachable (offline demo).
final List<_Achievement> _fallbackAchievements = [
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
  const _Achievement(
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
];

class AchievementsScreen extends ConsumerStatefulWidget {
  const AchievementsScreen({super.key});

  @override
  ConsumerState<AchievementsScreen> createState() => _AchievementsScreenState();
}

class _AchievementsScreenState extends ConsumerState<AchievementsScreen> {
  late ConfettiController _confettiController;

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

  /// Convert one backend achievement dict into the view model.
  _Achievement _fromJson(Map<String, dynamic> json) {
    final style = _styleFor((json['category'] ?? '').toString());
    final threshold = (json['threshold'] as num?)?.toInt() ?? 0;
    final current = (json['current'] as num?)?.toInt() ?? 0;
    final unlocked = json['unlocked'] == true;
    return _Achievement(
      id: (json['id'] ?? '').toString(),
      title: (json['name'] ?? '').toString(),
      description: (json['description'] ?? '').toString(),
      icon: style.icon,
      color: style.color,
      isUnlocked: unlocked,
      points: (json['reward'] as num?)?.toInt() ?? 0,
      progress: current,
      maxProgress: unlocked ? 0 : threshold,
    );
  }

  void _celebrate(_Achievement achievement) {
    _confettiController.play();
    showDialog(
      context: context,
      builder: (context) => _AchievementUnlockedDialog(achievement: achievement),
    );
  }

  @override
  Widget build(BuildContext context) {
    final asyncAchievements = ref.watch(achievementsProvider);
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
      body: asyncAchievements.when(
        loading: () => const Center(
          child: CircularProgressIndicator(color: AppColors.accent),
        ),
        error: (_, _) => _buildContent(_fallbackAchievements, offline: true),
        data: (payload) {
          final raw = payload['achievements'];
          final list = raw is List
              ? raw
                  .whereType<Map<String, dynamic>>()
                  .map(_fromJson)
                  .toList()
              : _fallbackAchievements;
          return _buildContent(list, offline: false);
        },
      ),
    );
  }

  Widget _buildContent(List<_Achievement> achievements, {required bool offline}) {
    final totalPoints = achievements
        .where((a) => a.isUnlocked)
        .fold(0, (sum, a) => sum + a.points);
    final unlockedCount = achievements.where((a) => a.isUnlocked).length;
    return Stack(
      children: [
        Column(
          children: [
            if (offline)
              Container(
                width: double.infinity,
                color: AppColors.orange.withValues(alpha: 0.15),
                padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 16),
                child: const Text(
                  'Offline — showing sample achievements',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.orange, fontSize: 12),
                ),
              ),
            _buildStatsHeader(totalPoints, unlockedCount, achievements.length),
            Expanded(
              child: RefreshIndicator(
                onRefresh: () async => ref.refresh(achievementsProvider.future),
                child: ListView.builder(
                  padding: const EdgeInsets.all(16),
                  itemCount: achievements.length,
                  itemBuilder: (context, index) {
                    return _AchievementCard(
                      achievement: achievements[index],
                      onTap: achievements[index].isUnlocked
                          ? () => _celebrate(achievements[index])
                          : null,
                    );
                  },
                ),
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
    );
  }

  Widget _buildStatsHeader(int totalPoints, int unlockedCount, int total) {
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
                  '$totalPoints',
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
                  '$unlockedCount / $total',
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
