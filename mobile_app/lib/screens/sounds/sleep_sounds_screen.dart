import 'package:flutter/material.dart';
import 'package:just_audio/just_audio.dart';
import '../../theme/app_theme.dart';

class SleepSoundsScreen extends StatefulWidget {
  const SleepSoundsScreen({super.key});

  @override
  State<SleepSoundsScreen> createState() => _SleepSoundsScreenState();
}

class _SleepSoundsScreenState extends State<SleepSoundsScreen> {
  String? _playingSound;
  double _volume = 0.7;
  late final AudioPlayer _player;

  final List<_Sound> _sounds = [
    const _Sound(
      id: '1',
      name: 'Ocean Waves',
      description: 'Gentle waves on a peaceful shore',
      icon: Icons.waves_rounded,
      color: AppColors.accent,
      isPremium: false,
      duration: '30 min',
    ),
    const _Sound(
      id: '2',
      name: 'Rain on Window',
      description: 'Soft rainfall with distant thunder',
      icon: Icons.cloud_rounded,
      color: AppColors.purple,
      isPremium: false,
      duration: '45 min',
    ),
    const _Sound(
      id: '3',
      name: 'Forest Night',
      description: 'Crickets and gentle wind in trees',
      icon: Icons.park_rounded,
      color: Colors.green,
      isPremium: false,
      duration: '60 min',
    ),
    const _Sound(
      id: '4',
      name: 'White Noise',
      description: 'Pure white noise for deep focus',
      icon: Icons.graphic_eq_rounded,
      color: AppColors.softWhite,
      isPremium: false,
      duration: 'Loop',
    ),
    const _Sound(
      id: '5',
      name: 'Quran Recitation',
      description: 'Peaceful Quran verses (Surah Al-Mulk)',
      icon: Icons.menu_book_rounded,
      color: AppColors.gold,
      isPremium: false,
      duration: '20 min',
    ),
    const _Sound(
      id: '6',
      name: 'Fireplace',
      description: 'Crackling fire in a cozy cabin',
      icon: Icons.local_fire_department_rounded,
      color: AppColors.orange,
      isPremium: true,
      duration: '60 min',
    ),
    const _Sound(
      id: '7',
      name: 'Meditation Bell',
      description: 'Tibetan singing bowls',
      icon: Icons.self_improvement_rounded,
      color: AppColors.purple,
      isPremium: true,
      duration: '15 min',
    ),
    const _Sound(
      id: '8',
      name: 'Cat Purring',
      description: 'Soothing purr sounds',
      icon: Icons.pets_rounded,
      color: AppColors.accent,
      isPremium: true,
      duration: 'Loop',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _player = AudioPlayer();
    _player.setVolume(_volume);
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  Future<void> _toggleSound(String soundId) async {
    if (_playingSound == soundId) {
      await _player.stop();
      setState(() => _playingSound = null);
    } else {
      setState(() => _playingSound = soundId);
      await _player.stop();
      try {
        await _player.setAsset('assets/sounds/$soundId.mp3');
        await _player.setLoopMode(LoopMode.one);
        await _player.play();
      } catch (_) {
        // Asset not yet bundled — UI still reflects playing state for preview.
      }
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
          'Sleep Sounds',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      body: Column(
        children: [
          if (_playingSound != null) _buildNowPlayingBar(),
          Expanded(
            child: GridView.builder(
              padding: const EdgeInsets.all(16),
              gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 2,
                childAspectRatio: 0.9,
                crossAxisSpacing: 12,
                mainAxisSpacing: 12,
              ),
              itemCount: _sounds.length,
              itemBuilder: (context, index) {
                final sound = _sounds[index];
                return _SoundCard(
                  sound: sound,
                  isPlaying: _playingSound == sound.id,
                  onTap: () => _toggleSound(sound.id),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNowPlayingBar() {
    final sound = _sounds.firstWhere((s) => s.id == _playingSound);
    
    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        gradient: LinearGradient(
          colors: [
            sound.color.withValues(alpha: 0.3),
            sound.color.withValues(alpha: 0.1),
          ],
        ),
        border: Border.all(color: sound.color.withValues(alpha: 0.5)),
      ),
      child: Column(
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: sound.color.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Icon(sound.icon, color: sound.color, size: 24),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      sound.name,
                      style: const TextStyle(
                        color: AppColors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      'Now Playing',
                      style: TextStyle(
                        color: sound.color.withValues(alpha: 0.8),
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              IconButton(
                onPressed: () => _toggleSound(sound.id),
                icon: const Icon(Icons.close_rounded),
                color: AppColors.white,
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Icon(Icons.volume_down_rounded,
                  color: AppColors.softWhite.withValues(alpha: 0.6), size: 20),
              Expanded(
                child: Slider(
                  value: _volume,
                  onChanged: (value) {
                    setState(() => _volume = value);
                    _player.setVolume(value);
                  },
                  activeColor: sound.color,
                  inactiveColor: AppColors.softWhite.withValues(alpha: 0.2),
                ),
              ),
              Icon(Icons.volume_up_rounded,
                  color: AppColors.softWhite.withValues(alpha: 0.6), size: 20),
              const SizedBox(width: 8),
              Text(
                '${(_volume * 100).toInt()}%',
                style: TextStyle(
                  color: sound.color,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _SoundCard extends StatelessWidget {
  const _SoundCard({
    required this.sound,
    required this.isPlaying,
    required this.onTap,
  });

  final _Sound sound;
  final bool isPlaying;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 300),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(20),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              sound.color.withValues(alpha: isPlaying ? 0.3 : 0.15),
              sound.color.withValues(alpha: isPlaying ? 0.15 : 0.05),
            ],
          ),
          border: Border.all(
            color: isPlaying ? sound.color : sound.color.withValues(alpha: 0.3),
            width: isPlaying ? 2 : 1,
          ),
          boxShadow: isPlaying
              ? [
                  BoxShadow(
                    color: sound.color.withValues(alpha: 0.4),
                    blurRadius: 16,
                    spreadRadius: 2,
                  )
                ]
              : [],
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: sound.color.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    sound.icon,
                    color: sound.color,
                    size: 28,
                  ),
                ),
                if (sound.isPremium)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 6,
                      vertical: 3,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.gold.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: AppColors.gold),
                    ),
                    child: const Row(
                      children: [
                        Icon(Icons.star_rounded, color: AppColors.gold, size: 10),
                        SizedBox(width: 2),
                        Text(
                          'PRO',
                          style: TextStyle(
                            color: AppColors.gold,
                            fontSize: 9,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  sound.name,
                  style: const TextStyle(
                    color: AppColors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  sound.description,
                  style: TextStyle(
                    color: AppColors.softWhite.withValues(alpha: 0.7),
                    fontSize: 11,
                    height: 1.3,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 8),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        Icon(
                          Icons.timer_rounded,
                          color: sound.color.withValues(alpha: 0.7),
                          size: 14,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          sound.duration,
                          style: TextStyle(
                            color: sound.color.withValues(alpha: 0.8),
                            fontSize: 11,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                    Icon(
                      isPlaying ? Icons.pause_circle_filled_rounded : Icons.play_circle_filled_rounded,
                      color: sound.color,
                      size: 28,
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Sound {
  const _Sound({
    required this.id,
    required this.name,
    required this.description,
    required this.icon,
    required this.color,
    required this.isPremium,
    required this.duration,
  });

  final String id;
  final String name;
  final String description;
  final IconData icon;
  final Color color;
  final bool isPremium;
  final String duration;
}
