import 'package:flutter/material.dart';
import '../../theme/app_theme.dart';

class SpotifyScreen extends StatefulWidget {
  const SpotifyScreen({super.key});

  @override
  State<SpotifyScreen> createState() => _SpotifyScreenState();
}

class _SpotifyScreenState extends State<SpotifyScreen> {
  bool _isConnected = false;
  bool _isPlaying = false;
  double _volume = 0.5;
  int? _sleepTimer;

  final _currentTrack = const _Track(
    title: 'Ocean Waves',
    artist: 'Nature Sounds',
    album: 'Sleep Collection',
    duration: Duration(minutes: 45),
    position: Duration(minutes: 12, seconds: 34),
  );

  final List<_Playlist> _playlists = const [
    _Playlist(
      id: '1',
      name: 'Sleep Deeply',
      trackCount: 50,
      imageUrl: '',
    ),
    _Playlist(
      id: '2',
      name: 'Meditation & Calm',
      trackCount: 32,
      imageUrl: '',
    ),
    _Playlist(
      id: '3',
      name: 'Ambient Chill',
      trackCount: 28,
      imageUrl: '',
    ),
  ];

  void _connectSpotify() {
    setState(() {
      _isConnected = true;
    });
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Spotify connected successfully!'),
        backgroundColor: AppColors.accent,
      ),
    );
  }

  void _togglePlayPause() {
    setState(() {
      _isPlaying = !_isPlaying;
    });
  }

  void _setSleepTimer(int? minutes) {
    setState(() {
      _sleepTimer = minutes;
    });
    if (minutes != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Sleep timer set for $minutes minutes'),
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
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.music_note_rounded,
              color: _isConnected ? AppColors.accent : AppColors.softWhite,
            ),
            const SizedBox(width: 8),
            const Text(
              'Spotify',
              style: TextStyle(fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
      body: !_isConnected ? _buildConnectView() : _buildPlayerView(),
    );
  }

  Widget _buildConnectView() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 120,
              height: 120,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppColors.cardBg,
                border: Border.all(
                  color: AppColors.accent.withValues(alpha: 0.3),
                  width: 2,
                ),
              ),
              child: const Icon(
                Icons.music_note_rounded,
                size: 64,
                color: AppColors.accent,
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'Connect to Spotify',
              style: TextStyle(
                color: AppColors.white,
                fontSize: 24,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            const Text(
              'Control your music directly from your smart bed. Play playlists, set sleep timers, and sync LED lights with the beat.',
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.softWhite,
                fontSize: 14,
                height: 1.5,
              ),
            ),
            const SizedBox(height: 32),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _connectSpotify,
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF1DB954),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(16),
                  ),
                ),
                icon: const Icon(Icons.music_note_rounded, size: 24),
                label: const Text(
                  'Connect Spotify Account',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
                ),
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Free & Premium Spotify accounts supported',
              style: TextStyle(
                color: AppColors.softWhite,
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPlayerView() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildNowPlayingCard(),
          const SizedBox(height: 20),
          _buildControlsCard(),
          const SizedBox(height: 20),
          _buildSleepTimerCard(),
          const SizedBox(height: 20),
          const Text(
            'Your Playlists',
            style: TextStyle(
              color: AppColors.white,
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 12),
          ..._playlists.map((playlist) => _PlaylistCard(playlist: playlist)),
        ],
      ),
    );
  }

  Widget _buildNowPlayingCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF1A2640), Color(0xFF0F1B2F)],
        ),
        border: Border.all(
          color: AppColors.accent.withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        children: [
          Container(
            width: 140,
            height: 140,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              color: AppColors.cardBg,
              boxShadow: [
                BoxShadow(
                  color: AppColors.accent.withValues(alpha: 0.2),
                  blurRadius: 20,
                  spreadRadius: 2,
                ),
              ],
            ),
            child: const Icon(
              Icons.album_rounded,
              size: 64,
              color: AppColors.accent,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            _currentTrack.title,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.white,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            _currentTrack.artist,
            style: const TextStyle(
              color: AppColors.accent,
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 16),
          ClipRRect(
            borderRadius: BorderRadius.circular(99),
            child: LinearProgressIndicator(
              value: _currentTrack.position.inSeconds /
                  _currentTrack.duration.inSeconds,
              minHeight: 6,
              backgroundColor: AppColors.cardBg,
              valueColor: const AlwaysStoppedAnimation<Color>(AppColors.accent),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                _formatDuration(_currentTrack.position),
                style: const TextStyle(
                  color: AppColors.softWhite,
                  fontSize: 12,
                ),
              ),
              Text(
                _formatDuration(_currentTrack.duration),
                style: const TextStyle(
                  color: AppColors.softWhite,
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildControlsCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              IconButton(
                onPressed: () {},
                icon: const Icon(Icons.skip_previous_rounded),
                color: AppColors.white,
                iconSize: 36,
              ),
              Container(
                width: 64,
                height: 64,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.accent,
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.accent.withValues(alpha: 0.4),
                      blurRadius: 16,
                      spreadRadius: 2,
                    ),
                  ],
                ),
                child: IconButton(
                  onPressed: _togglePlayPause,
                  icon: Icon(
                    _isPlaying ? Icons.pause_rounded : Icons.play_arrow_rounded,
                    size: 32,
                  ),
                  color: AppColors.background,
                ),
              ),
              IconButton(
                onPressed: () {},
                icon: const Icon(Icons.skip_next_rounded),
                color: AppColors.white,
                iconSize: 36,
              ),
            ],
          ),
          const SizedBox(height: 24),
          Row(
            children: [
              const Icon(
                Icons.volume_down_rounded,
                color: AppColors.softWhite,
                size: 20,
              ),
              Expanded(
                child: Slider(
                  value: _volume,
                  onChanged: (val) => setState(() => _volume = val),
                  activeColor: AppColors.accent,
                  inactiveColor: AppColors.softWhite.withValues(alpha: 0.3),
                ),
              ),
              const Icon(
                Icons.volume_up_rounded,
                color: AppColors.softWhite,
                size: 20,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildSleepTimerCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.timer_rounded, color: AppColors.accent, size: 20),
              const SizedBox(width: 8),
              const Text(
                'Sleep Timer',
                style: TextStyle(
                  color: AppColors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              if (_sleepTimer != null)
                Text(
                  '$_sleepTimer min',
                  style: const TextStyle(
                    color: AppColors.accent,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _TimerChip(
                label: '15 min',
                minutes: 15,
                isSelected: _sleepTimer == 15,
                onTap: () => _setSleepTimer(15),
              ),
              _TimerChip(
                label: '30 min',
                minutes: 30,
                isSelected: _sleepTimer == 30,
                onTap: () => _setSleepTimer(30),
              ),
              _TimerChip(
                label: '45 min',
                minutes: 45,
                isSelected: _sleepTimer == 45,
                onTap: () => _setSleepTimer(45),
              ),
              _TimerChip(
                label: '60 min',
                minutes: 60,
                isSelected: _sleepTimer == 60,
                onTap: () => _setSleepTimer(60),
              ),
              if (_sleepTimer != null)
                _TimerChip(
                  label: 'Off',
                  minutes: null,
                  isSelected: false,
                  onTap: () => _setSleepTimer(null),
                ),
            ],
          ),
        ],
      ),
    );
  }

  String _formatDuration(Duration duration) {
    final minutes = duration.inMinutes.toString().padLeft(2, '0');
    final seconds = (duration.inSeconds % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }
}

class _PlaylistCard extends StatelessWidget {
  const _PlaylistCard({required this.playlist});

  final _Playlist playlist;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: () {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: Text('Playing ${playlist.name}'),
                backgroundColor: AppColors.accent,
              ),
            );
          },
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.cardBg,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(10),
                    color: AppColors.background,
                  ),
                  child: const Icon(
                    Icons.library_music_rounded,
                    color: AppColors.accent,
                    size: 28,
                  ),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        playlist.name,
                        style: const TextStyle(
                          color: AppColors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        '${playlist.trackCount} tracks',
                        style: const TextStyle(
                          color: AppColors.softWhite,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                const Icon(
                  Icons.play_circle_filled_rounded,
                  color: AppColors.accent,
                  size: 32,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TimerChip extends StatelessWidget {
  const _TimerChip({
    required this.label,
    required this.minutes,
    required this.isSelected,
    required this.onTap,
  });

  final String label;
  final int? minutes;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected ? AppColors.accent : AppColors.background,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? AppColors.accent : AppColors.softWhite,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isSelected ? AppColors.background : AppColors.softWhite,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}

class _Track {
  const _Track({
    required this.title,
    required this.artist,
    required this.album,
    required this.duration,
    required this.position,
  });

  final String title;
  final String artist;
  final String album;
  final Duration duration;
  final Duration position;
}

class _Playlist {
  const _Playlist({
    required this.id,
    required this.name,
    required this.trackCount,
    required this.imageUrl,
  });

  final String id;
  final String name;
  final int trackCount;
  final String imageUrl;
}
