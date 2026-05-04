import 'dart:io' show Platform;
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:shimmer/shimmer.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/glass_card.dart';
import '../winddown/winddown_journey_screen.dart';
import '../alarm/alarm_screen.dart';
import '../spotify/spotify_screen.dart';
import '../dana/dana_chat_screen.dart';
import '../led/led_control_screen.dart';
import '../scenes/scenes_gallery_screen.dart';
import '../achievements/achievements_screen.dart';
import '../journal/sleep_journal_screen.dart';
import '../health/health_dashboard_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with TickerProviderStateMixin {
  bool _isLoading = true;
  String? _errorMessage;
  Map<String, dynamic> _dashboard = <String, dynamic>{};
  Map<String, dynamic> _deviceStatus = <String, dynamic>{};
  String _userName = 'User';
  late AnimationController _scoreAnimationController;
  late Animation<double> _scoreAnimation;
  late AnimationController _bgAnimController;
  late AnimationController _staggerController;
  Map<String, dynamic>? _updateInfo;
  Map<String, dynamic>? _smartInsight;
  List<Map<String, dynamic>> _activityFeed = [];

  static const List<_ActionItem> _actions = [
    _ActionItem(icon: Icons.nightlight_round, label: 'Wind-Down', color: AppColors.purple),
    _ActionItem(icon: Icons.lightbulb_rounded, label: 'LED Control', color: AppColors.accent),
    _ActionItem(icon: Icons.music_note_rounded, label: 'Spotify', color: Color(0xFF1DB954)),
    _ActionItem(icon: Icons.alarm_rounded, label: 'Alarms', color: AppColors.orange),
    _ActionItem(icon: Icons.palette_rounded, label: 'Scenes', color: AppColors.purple),
    _ActionItem(icon: Icons.chat_bubble_rounded, label: 'Dana Chat', color: AppColors.gold),
    _ActionItem(icon: Icons.emoji_events_rounded, label: 'Achievements', color: AppColors.gold),
    _ActionItem(icon: Icons.edit_note_rounded, label: 'Journal', color: AppColors.purple),
    _ActionItem(icon: Icons.monitor_heart_rounded, label: 'Health', color: Color(0xFF1DB954)),
  ];

  @override
  void initState() {
    super.initState();
    _scoreAnimationController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    );
    _scoreAnimation = Tween<double>(begin: 0, end: 0).animate(
      CurvedAnimation(parent: _scoreAnimationController, curve: Curves.easeOutCubic),
    );
    _bgAnimController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 6),
    )..repeat(reverse: true);
    _staggerController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _loadData();
  }

  @override
  void dispose() {
    _scoreAnimationController.dispose();
    _bgAnimController.dispose();
    _staggerController.dispose();
    super.dispose();
  }

  Animation<double> _cardAnim(int index) => CurvedAnimation(
        parent: _staggerController,
        curve: Interval(
          (index * 0.08).clamp(0.0, 0.8),
          (index * 0.08 + 0.5).clamp(0.0, 1.0),
          curve: Curves.easeOutCubic,
        ),
      );

  String _userFriendlyError(Object e) {
    final raw = e.toString().toLowerCase();
    if (raw.contains('timeout') || raw.contains('timed out')) {
      return 'Connection timed out. Check your network.';
    }
    if (raw.contains('socket') || raw.contains('connection') || raw.contains('network') || raw.contains('reach')) {
      return 'Cannot reach the server. Check your network.';
    }
    if (raw.contains('unauthorized') || raw.contains('401') || raw.contains('sign in')) {
      return 'Session expired. Please sign in again.';
    }
    if (raw.contains('not found') || raw.contains('404')) {
      return 'Data not available. Pull down to retry.';
    }
    if (raw.contains('server') || raw.contains('500')) {
      return 'Server error. Please try again later.';
    }
    return 'Could not load data. Pull down to retry.';
  }

  Future<void> _loadData() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final results = await Future.wait([
        ApiService.getDashboard(),
        ApiService.getDeviceStatus(),
        ApiService.getUserMe(),
      ]);

      final dashboardData = results[0];
      final deviceData = results[1];
      final userData = results[2];

      if (!mounted) return;

      final allFailed = dashboardData['error'] == true &&
          deviceData['error'] == true &&
          userData['error'] == true;
      if (allFailed) {
        throw Exception(dashboardData['message'] ?? 'Could not reach the server');
      }

      setState(() {
        if (dashboardData['error'] != true) {
          _dashboard = dashboardData;
          _userName = dashboardData['name'] ?? _userName;

          final weeklyInsight = dashboardData['weekly_insight'] ?? {};
          final newScore = (weeklyInsight['completion_rate_pct'] ?? 0).toDouble();
          _scoreAnimation = Tween<double>(
            begin: _scoreAnimation.value,
            end: newScore / 100,
          ).animate(
            CurvedAnimation(parent: _scoreAnimationController, curve: Curves.easeOutCubic),
          );
          _scoreAnimationController.forward(from: 0);
        }
        if (deviceData['error'] != true) _deviceStatus = deviceData;
        if (userData['error'] != true) {
          final name = userData['name'] ?? userData['full_name'] ?? '';
          if (name.isNotEmpty) _userName = name;
        }
        _isLoading = false;
      });

      _staggerController.forward(from: 0);
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = _userFriendlyError(e);
          _isLoading = false;
        });
      }
    }

    // These load independently — never block the main UI
    _checkForUpdate();
    _loadSmartInsight();
    _loadActivityFeed();
  }

  Future<void> _loadSmartInsight() async {
    try {
      final result = await ApiService.getSmartSleepInsight();
      if (mounted && result['error'] != true && result['headline'] != null) {
        setState(() => _smartInsight = result);
      }
    } catch (_) {}
  }

  Future<void> _loadActivityFeed() async {
    try {
      final result = await ApiService.getDanaActivityFeed();
      if (mounted && result['error'] != true) {
        final items = result['items'];
        if (items is List) {
          setState(() {
            _activityFeed = items.whereType<Map<String, dynamic>>().take(5).toList();
          });
        }
      }
    } catch (_) {}
  }

  Future<void> _checkForUpdate() async {
    try {
      final String platform = Platform.isIOS ? 'ios' : 'android';
      final Map<String, dynamic>? info = await ApiService.checkForUpdate(platform);
      if (info != null && mounted) {
        setState(() => _updateInfo = info);
        if (info['is_required'] == true) _showRequiredUpdateDialog(info);
      }
    } catch (_) {}
  }

  void _showRequiredUpdateDialog(Map<String, dynamic> info) {
    if (!mounted) return;
    final versionRaw = info['version'];
    final version = (versionRaw is String && RegExp(r'^\d+\.\d+').hasMatch(versionRaw))
        ? versionRaw
        : 'a new version';
    final changelog = (info['changelog'] as List?)?.take(3).join('\n') ?? '';
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('Update Required'),
        content: Text(
          '$version is required to continue.\n\n$changelog'.trim(),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Later'),
          ),
          TextButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              _launchStore(info);
            },
            child: const Text('Update Now'),
          ),
        ],
      ),
    );
  }

  Future<void> _launchStore(Map<String, dynamic> info) async {
    final String? url = info['store_url'] as String?;
    if (url != null && url.isNotEmpty) {
      final Uri uri = Uri.parse(url);
      if (await canLaunchUrl(uri)) await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }

  void _handleActionTap(String label) {
    Widget? screen;
    switch (label) {
      case 'Wind-Down':
        screen = const WindDownJourneyScreen();
      case 'LED Control':
        screen = const LedControlScreen();
      case 'Spotify':
        screen = const SpotifyScreen();
      case 'Alarms':
        screen = const AlarmScreen();
      case 'Scenes':
        screen = const ScenesGalleryScreen();
      case 'Dana Chat':
        screen = const DanaChatScreen();
      case 'Achievements':
        screen = const AchievementsScreen();
      case 'Journal':
        screen = const SleepJournalScreen();
      case 'Health':
        screen = const HealthDashboardScreen();
    }
    if (screen != null) {
      Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => screen!));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: Stack(
        children: [
          // Animated gradient background — slow living pulse
          AnimatedBuilder(
            animation: _bgAnimController,
            builder: (_, __) => Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color.lerp(const Color(0xFF0A1628), const Color(0xFF0D1F3C),
                        _bgAnimController.value)!,
                    Color.lerp(const Color(0xFF0F2040), const Color(0xFF1A1040),
                        _bgAnimController.value)!,
                    const Color(0xFF0A1628),
                  ],
                  stops: const [0.0, 0.5, 1.0],
                ),
              ),
            ),
          ),
          SafeArea(
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
                    onRefresh: _loadData,
                    child: SingleChildScrollView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _buildTopBar(),
                          if (_updateInfo != null && _updateInfo!['is_required'] != true) ...[
                            const SizedBox(height: 10),
                            _buildUpdateBanner(_updateInfo!),
                          ],
                          if (_errorMessage != null) ...[
                            const SizedBox(height: 12),
                            _buildErrorBanner(),
                          ],
                          const SizedBox(height: 20),
                          if (_smartInsight != null) ...[
                            _buildSmartInsightCard()
                                .animate()
                                .fadeIn(duration: 350.ms)
                                .slideY(begin: 0.08, end: 0, duration: 350.ms),
                            const SizedBox(height: 14),
                          ],
                          _buildDanaGreetingCard()
                              .animate()
                              .fadeIn(duration: 400.ms)
                              .slideY(begin: 0.1, end: 0, duration: 400.ms),
                          const SizedBox(height: 16),
                          _buildSleepScoreCircle()
                              .animate()
                              .fadeIn(delay: 100.ms, duration: 400.ms)
                              .slideY(begin: 0.1, end: 0, delay: 100.ms, duration: 400.ms),
                          const SizedBox(height: 16),
                          _buildQuickStatsRow()
                              .animate()
                              .fadeIn(delay: 200.ms, duration: 400.ms)
                              .slideY(begin: 0.1, end: 0, delay: 200.ms, duration: 400.ms),
                          if (_activityFeed.isNotEmpty) ...[
                            const SizedBox(height: 16),
                            _buildDanaActivityFeed()
                                .animate()
                                .fadeIn(delay: 300.ms, duration: 400.ms),
                          ],
                          const SizedBox(height: 16),
                          _buildQuickActionsGrid()
                              .animate()
                              .fadeIn(delay: 350.ms, duration: 450.ms)
                              .slideY(begin: 0.08, end: 0, delay: 350.ms, duration: 450.ms),
                          const SizedBox(height: 20),
                          _buildIslamicSection()
                              .animate()
                              .fadeIn(delay: 450.ms, duration: 400.ms),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ─── Smart Insight Card (AI bedtime headline) ───────────────────────────────

  Widget _buildSmartInsightCard() {
    final String headline = _smartInsight?['headline'] as String? ?? '';
    return GlassCard(
      borderRadius: 18,
      padding: const EdgeInsets.all(14),
      border: Border.all(color: AppColors.accent.withValues(alpha: 0.45), width: 1.5),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              gradient: LinearGradient(colors: [
                AppColors.accent.withValues(alpha: 0.2),
                AppColors.purple.withValues(alpha: 0.2),
              ]),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.auto_awesome, color: AppColors.accent, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              headline,
              style: const TextStyle(
                color: AppColors.white,
                fontSize: 13,
                height: 1.5,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }

  // ─── Dana Activity Feed (horizontal scroll) ────────────────────────────────

  Widget _buildDanaActivityFeed() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'Dana Activity',
          style: TextStyle(
            color: AppColors.softWhite,
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        SizedBox(
          height: 78,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: _activityFeed.length,
            separatorBuilder: (_, __) => const SizedBox(width: 8),
            itemBuilder: (_, i) {
              final item = _activityFeed[i];
              final status = item['status'] as String? ?? 'info';
              final dotColor = _statusColor(status);
              final eventText = item['event'] as String? ?? '';
              final timeText = item['time'] as String? ?? '';
              return GlassCard(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                borderRadius: 14,
                child: SizedBox(
                  width: 160,
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            width: 7,
                            height: 7,
                            decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
                          ),
                          const SizedBox(width: 6),
                          Text(
                            timeText,
                            style: TextStyle(
                              color: dotColor,
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      GestureDetector(
                        onTap: eventText.length > 38
                            ? () => showDialog<void>(
                                  context: context,
                                  builder: (_) => AlertDialog(
                                    backgroundColor: const Color(0xFF0F2040),
                                    content: Text(
                                      eventText,
                                      style: const TextStyle(color: AppColors.softWhite, fontSize: 13),
                                    ),
                                    actions: [
                                      TextButton(
                                        onPressed: () => Navigator.of(context).pop(),
                                        child: const Text('Close'),
                                      ),
                                    ],
                                  ),
                                )
                            : null,
                        child: Text(
                          eventText,
                          style: const TextStyle(color: AppColors.softWhite, fontSize: 11, height: 1.4),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'completed':
        return Colors.green;
      case 'queued':
        return AppColors.orange;
      case 'ready':
        return AppColors.accent;
      default:
        return AppColors.softWhite;
    }
  }

  // ─── Top Bar ───────────────────────────────────────────────────────────────

  Widget _buildTopBar() {
    final hour = DateTime.now().hour;
    final String greeting = hour < 12
        ? 'Good Morning'
        : hour < 18
            ? 'Good Afternoon'
            : 'Good Evening';
    final deviceOnline = _deviceStatus['device_online'] == true;

    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    '$greeting, $_userName',
                    style: const TextStyle(
                      color: AppColors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(width: 6),
                  const Icon(Icons.nightlight_round, color: AppColors.softWhite, size: 18),
                ],
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 400),
                    width: 8,
                    height: 8,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: deviceOnline ? Colors.green : Colors.red,
                      boxShadow: [
                        BoxShadow(
                          color: (deviceOnline ? Colors.green : Colors.red).withValues(alpha: 0.5),
                          blurRadius: 6,
                          spreadRadius: 1,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 6),
                  Text(
                    deviceOnline ? 'Bed Online' : 'Bed Offline',
                    style: TextStyle(
                      color: deviceOnline ? Colors.green : Colors.red,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        GlassCard(
          padding: EdgeInsets.zero,
          borderRadius: 12,
          border: Border.all(color: AppColors.accent.withValues(alpha: 0.35)),
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

  // ─── Dana Greeting Card ───────────────────────────────────────────────────

  Widget _buildDanaGreetingCard() {
    return GlassCard(
      borderRadius: 20,
      padding: const EdgeInsets.all(16),
      border: Border.all(color: AppColors.accent.withValues(alpha: 0.3)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.nightlight_round, color: AppColors.accent, size: 18),
              const SizedBox(width: 8),
              const Expanded(
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
          Shimmer.fromColors(
            baseColor: AppColors.accent,
            highlightColor: Colors.white,
            child: const Text(
              'Dana Guide · Active',
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }

  // ─── Sleep Score Circle with Glow Ring ───────────────────────────────────

  Widget _buildSleepScoreCircle() {
    final weeklyInsight = _dashboard['weekly_insight'] ?? {};
    return AnimatedBuilder(
      animation: Listenable.merge([_scoreAnimation, _bgAnimController]),
      builder: (context, child) {
        final scoreColor = _scoreAnimation.value > 0.7
            ? Colors.green
            : _scoreAnimation.value > 0.5
                ? AppColors.accent
                : AppColors.orange;
        return GlassCard(
          borderRadius: 20,
          padding: const EdgeInsets.all(20),
          border: Border.all(color: AppColors.accent.withValues(alpha: 0.25)),
          child: Column(
            children: [
              const Text(
                'Weekly Sleep Score',
                style: TextStyle(
                  color: AppColors.softWhite,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: 160,
                height: 160,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    // Glow ring behind the progress indicator
                    CustomPaint(
                      size: const Size(160, 160),
                      painter: _GlowRingPainter(
                        progress: _scoreAnimation.value,
                        glowOpacity: 0.15 + (_bgAnimController.value * 0.2),
                        color: scoreColor,
                      ),
                    ),
                    SizedBox(
                      width: 160,
                      height: 160,
                      child: CircularProgressIndicator(
                        value: _scoreAnimation.value,
                        strokeWidth: 12,
                        backgroundColor: AppColors.background.withValues(alpha: 0.6),
                        valueColor: AlwaysStoppedAnimation<Color>(scoreColor),
                      ),
                    ),
                    Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '${(_scoreAnimation.value * 100).toInt()}',
                          style: TextStyle(
                            color: scoreColor,
                            fontSize: 48,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const Text(
                          'Score',
                          style: TextStyle(
                            color: AppColors.softWhite,
                            fontSize: 14,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Text(
                weeklyInsight['summary'] ?? 'Keep up the great work!',
                textAlign: TextAlign.center,
                style: const TextStyle(color: AppColors.softWhite, fontSize: 13, height: 1.4),
              ),
            ],
          ),
        );
      },
    );
  }

  // ─── Quick Stats Row ──────────────────────────────────────────────────────

  Widget _buildQuickStatsRow() {
    final weeklyInsight = _dashboard['weekly_insight'] ?? {};
    final nightly = _dashboard['nightly_summary'] ?? {};

    final String lastNight = (nightly['last_night_hours'] ?? '7.2h').toString();
    final String sleepScore = (weeklyInsight['completion_rate_pct'] ?? '82').toString();
    final String streak = (weeklyInsight['wind_down_sessions'] ?? '5').toString();

    return Row(
      children: [
        Expanded(child: _StatCard(label: 'Last Night', value: lastNight, accentColor: AppColors.accent)),
        const SizedBox(width: 10),
        Expanded(child: _StatCard(label: 'Sleep Score', value: sleepScore, accentColor: AppColors.purple)),
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

  // ─── Quick Actions Grid with Stagger Animation ────────────────────────────

  Widget _buildQuickActionsGrid() {
    final List<Widget> items = List.generate(_actions.length, (i) {
      final action = _actions[i];
      return AnimatedBuilder(
        animation: _staggerController,
        builder: (_, child) => FadeTransition(
          opacity: _cardAnim(i),
          child: SlideTransition(
            position: Tween<Offset>(
              begin: const Offset(0, 0.15),
              end: Offset.zero,
            ).animate(_cardAnim(i)),
            child: child,
          ),
        ),
        child: _QuickActionCard(
          icon: action.icon,
          label: action.label,
          color: action.color,
          onTap: () => _handleActionTap(action.label),
        ),
      );
    });

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 12,
      crossAxisSpacing: 12,
      childAspectRatio: 1.5,
      children: items,
    );
  }

  // ─── Islamic Section ──────────────────────────────────────────────────────

  Widget _buildIslamicSection() {
    final String nextPrayer = (_dashboard['next_prayer'] ?? 'Isha').toString();
    final String prayerCountdown = (_dashboard['next_prayer_eta'] ?? 'in 45 minutes').toString();

    return GlassCard(
      borderRadius: 18,
      padding: const EdgeInsets.all(16),
      border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.accent.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.mosque_rounded, color: AppColors.softWhite, size: 20),
          ),
          const SizedBox(width: 14),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Next Prayer',
                style: TextStyle(color: AppColors.softWhite, fontSize: 12, fontWeight: FontWeight.w500),
              ),
              const SizedBox(height: 2),
              Text(
                nextPrayer,
                style: const TextStyle(color: AppColors.white, fontSize: 20, fontWeight: FontWeight.w700),
              ),
              Text(
                prayerCountdown,
                style: const TextStyle(color: AppColors.accent, fontSize: 13, fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ─── Banners ──────────────────────────────────────────────────────────────

  Widget _buildErrorBanner() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.orange.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.orange.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off_rounded, color: AppColors.orange, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _errorMessage ?? 'Could not load data.',
              style: const TextStyle(color: AppColors.orange, fontSize: 12),
            ),
          ),
          TextButton(
            onPressed: _loadData,
            style: TextButton.styleFrom(
              foregroundColor: AppColors.orange,
              visualDensity: VisualDensity.compact,
              padding: const EdgeInsets.symmetric(horizontal: 8),
            ),
            child: const Text('Retry', style: TextStyle(fontSize: 12)),
          ),
        ],
      ),
    );
  }

  Widget _buildUpdateBanner(Map<String, dynamic> info) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      decoration: BoxDecoration(
        color: const Color(0xFFC79A55).withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFC79A55).withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          const Icon(Icons.system_update_rounded, color: Color(0xFFC79A55), size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Update available — v${info['version'] ?? ''}',
                  style: const TextStyle(
                    color: Color(0xFF7A5A1E),
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if ((info['changelog'] as List?)?.isNotEmpty == true)
                  Text(
                    (info['changelog'] as List).first.toString(),
                    style: const TextStyle(color: Color(0xFF9B7A3A), fontSize: 11),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
          TextButton(
            onPressed: () => _launchStore(info),
            style: TextButton.styleFrom(
              foregroundColor: const Color(0xFFC79A55),
              visualDensity: VisualDensity.compact,
              padding: const EdgeInsets.symmetric(horizontal: 8),
            ),
            child: const Text('Update', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700)),
          ),
          IconButton(
            onPressed: () => setState(() => _updateInfo = null),
            icon: const Icon(Icons.close, size: 16, color: Color(0xFF9B7A3A)),
            visualDensity: VisualDensity.compact,
            padding: EdgeInsets.zero,
          ),
        ],
      ),
    );
  }
}

// ─── Glow Ring Painter ─────────────────────────────────────────────────────

class _GlowRingPainter extends CustomPainter {
  const _GlowRingPainter({
    required this.progress,
    required this.glowOpacity,
    required this.color,
  });

  final double progress;
  final double glowOpacity;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (progress <= 0) return;
    final center = Offset(size.width / 2, size.height / 2);
    final radius = (size.width - 12) / 2;
    final startAngle = -math.pi / 2;
    final sweepAngle = 2 * math.pi * progress;

    final glowPaint = Paint()
      ..color = color.withOpacity(glowOpacity.clamp(0.0, 1.0))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 24
      ..strokeCap = StrokeCap.round
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 12);

    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      startAngle,
      sweepAngle,
      false,
      glowPaint,
    );
  }

  @override
  bool shouldRepaint(_GlowRingPainter old) =>
      old.progress != progress || old.glowOpacity != glowOpacity || old.color != color;
}

// ─── Action Item Model ────────────────────────────────────────────────────

class _ActionItem {
  const _ActionItem({required this.icon, required this.label, required this.color});
  final IconData icon;
  final String label;
  final Color color;
}

// ─── Stat Card ────────────────────────────────────────────────────────────

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
    return GlassCard(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
      borderRadius: 14,
      border: Border.all(color: accentColor.withValues(alpha: 0.2)),
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
                Icon(trailingIcon, size: 16, color: accentColor),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

// ─── Quick Action Card ────────────────────────────────────────────────────

class _QuickActionCard extends StatelessWidget {
  const _QuickActionCard({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: GlassCard(
          padding: const EdgeInsets.all(14),
          borderRadius: 16,
          border: Border.all(color: color.withValues(alpha: 0.35), width: 1.5),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: Icon(icon, color: color, size: 28),
              ),
              const SizedBox(height: 10),
              Text(
                label,
                style: const TextStyle(
                  color: AppColors.white,
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
}
