import 'dart:io' show Platform;
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:shimmer/shimmer.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/cached_avatar.dart';
import '../../widgets/glass_card.dart';
import '../../widgets/network_banner.dart';
import '../../widgets/live_sensor_card.dart';
import '../../widgets/shimmer_loader.dart';

// ─── Data models ─────────────────────────────────────────────────────────────

class _HomeData {
  const _HomeData({
    required this.dashboard,
    required this.device,
    required this.userName,
    this.profileImageUrl,
  });
  final Map<String, dynamic> dashboard;
  final Map<String, dynamic> device;
  final String userName;
  final String? profileImageUrl;
}

// ─── Providers ───────────────────────────────────────────────────────────────

final homeDashboardProvider = FutureProvider.autoDispose<_HomeData>((ref) async {
  final results = await Future.wait([
    ApiService.getDashboard(),
    ApiService.getDeviceStatus(),
    ApiService.getUserMe(),
  ]);
  final dashData = results[0];
  final deviceData = results[1];
  final userData = results[2];

  final allFailed = dashData['error'] == true &&
      deviceData['error'] == true &&
      userData['error'] == true;
  if (allFailed) {
    throw Exception(dashData['message'] ?? 'Could not reach the server');
  }

  String userName = 'User';
  if (dashData['error'] != true) {
    userName = dashData['name'] as String? ?? userName;
  }
  if (userData['error'] != true) {
    final name = userData['name'] as String? ?? userData['full_name'] as String? ?? '';
    if (name.isNotEmpty) userName = name;
  }

  return _HomeData(
    dashboard: dashData['error'] != true ? dashData : <String, dynamic>{},
    device: deviceData['error'] != true ? deviceData : <String, dynamic>{},
    userName: userName,
    profileImageUrl: userData['profile_image'] as String? ??
        userData['avatar_url'] as String?,
  );
});

final homeSmartInsightProvider =
    FutureProvider.autoDispose<Map<String, dynamic>?>((ref) async {
  try {
    final result = await ApiService.getSmartSleepInsight();
    if (result['error'] != true && result['headline'] != null) return result;
  } catch (_) {}
  return null;
});

final homeActivityFeedProvider =
    FutureProvider.autoDispose<List<Map<String, dynamic>>>((ref) async {
  try {
    final result = await ApiService.getDanaActivityFeed();
    if (result['error'] != true) {
      final items = result['items'];
      if (items is List) {
        return items.whereType<Map<String, dynamic>>().take(5).toList();
      }
    }
  } catch (_) {}
  return const [];
});

// ─── Screen ───────────────────────────────────────────────────────────────────

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen>
    with TickerProviderStateMixin {
  late AnimationController _scoreAnimCtrl;
  late Animation<double> _scoreAnim;
  late AnimationController _bgAnimCtrl;
  late AnimationController _staggerCtrl;
  Map<String, dynamic>? _updateInfo;

  static const List<_ActionItem> _actions = [
    _ActionItem(
      icon: Icons.nightlight_round,
      label: 'Wind-Down',
      color: AppColors.purple,
      route: '/winddown',
    ),
    _ActionItem(
      icon: Icons.lightbulb_rounded,
      label: 'LED Control',
      color: AppColors.accent,
      route: '/led',
    ),
    _ActionItem(
      icon: Icons.music_note_rounded,
      label: 'Spotify',
      color: Color(0xFF1DB954),
      route: '/spotify',
    ),
    _ActionItem(
      icon: Icons.alarm_rounded,
      label: 'Alarms',
      color: AppColors.orange,
      route: '/alarm',
    ),
    _ActionItem(
      icon: Icons.palette_rounded,
      label: 'Scenes',
      color: AppColors.purple,
      route: '/scenes-gallery',
    ),
    _ActionItem(
      icon: Icons.chat_bubble_rounded,
      label: 'Dana Chat',
      color: AppColors.gold,
      route: '/dana-chat',
    ),
    _ActionItem(
      icon: Icons.emoji_events_rounded,
      label: 'Achievements',
      color: AppColors.gold,
      route: '/achievements',
    ),
    _ActionItem(
      icon: Icons.edit_note_rounded,
      label: 'Journal',
      color: AppColors.purple,
      route: '/journal',
    ),
    _ActionItem(
      icon: Icons.monitor_heart_rounded,
      label: 'Health',
      color: Color(0xFF1DB954),
      route: '/health',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _scoreAnimCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    );
    _scoreAnim = Tween<double>(begin: 0, end: 0).animate(
      CurvedAnimation(parent: _scoreAnimCtrl, curve: Curves.easeOutCubic),
    );
    _bgAnimCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 6),
    )..repeat(reverse: true);
    _staggerCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _checkForUpdate();
  }

  @override
  void dispose() {
    _scoreAnimCtrl.dispose();
    _bgAnimCtrl.dispose();
    _staggerCtrl.dispose();
    super.dispose();
  }

  Animation<double> _cardAnim(int index) => CurvedAnimation(
        parent: _staggerCtrl,
        curve: Interval(
          (index * 0.08).clamp(0.0, 0.8),
          (index * 0.08 + 0.5).clamp(0.0, 1.0),
          curve: Curves.easeOutCubic,
        ),
      );

  Future<void> _onRefresh() async {
    ref.invalidate(homeDashboardProvider);
    ref.invalidate(homeSmartInsightProvider);
    ref.invalidate(homeActivityFeedProvider);
  }

  String _userFriendlyError(Object e) {
    final raw = e.toString().toLowerCase();
    if (raw.contains('timeout') || raw.contains('timed out')) {
      return 'Connection timed out. Check your network.';
    }
    if (raw.contains('socket') ||
        raw.contains('connection') ||
        raw.contains('network') ||
        raw.contains('reach')) {
      return 'Cannot reach the server. Check your network.';
    }
    if (raw.contains('unauthorized') ||
        raw.contains('401') ||
        raw.contains('sign in')) {
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

  Future<void> _checkForUpdate() async {
    try {
      final String platform = Platform.isIOS ? 'ios' : 'android';
      final Map<String, dynamic>? info =
          await ApiService.checkForUpdate(platform);
      if (info != null && mounted) {
        setState(() => _updateInfo = info);
        if (info['is_required'] == true) _showRequiredUpdateDialog(info);
      }
    } catch (_) {}
  }

  void _showRequiredUpdateDialog(Map<String, dynamic> info) {
    if (!mounted) return;
    final versionRaw = info['version'];
    final version =
        (versionRaw is String && RegExp(r'^\d+\.\d+').hasMatch(versionRaw))
            ? versionRaw
            : 'a new version';
    final changelog =
        (info['changelog'] as List?)?.take(3).join('\n') ?? '';
    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        title: const Text('Update Required'),
        content: Text('$version is required to continue.\n\n$changelog'.trim()),
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
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final dashAsync = ref.watch(homeDashboardProvider);
    final smartInsight = ref.watch(homeSmartInsightProvider).valueOrNull;
    final activityFeed =
        ref.watch(homeActivityFeedProvider).valueOrNull ?? const [];

    // Trigger score + stagger animations when data arrives
    ref.listen<AsyncValue<_HomeData>>(homeDashboardProvider, (_, next) {
      next.whenData((data) {
        final double score = ((data.dashboard['weekly_insight']
                    ?['completion_rate_pct'] ??
                0) as num)
            .toDouble();
        _scoreAnim = Tween<double>(
          begin: _scoreAnim.value,
          end: score / 100,
        ).animate(
          CurvedAnimation(
              parent: _scoreAnimCtrl, curve: Curves.easeOutCubic),
        );
        _scoreAnimCtrl.forward(from: 0);
        _staggerCtrl.forward(from: 0);
      });
    });

    final homeData = dashAsync.valueOrNull;

    return Scaffold(
      backgroundColor: AppColors.background,
      body: Stack(
        children: [
          // Animated gradient background
          AnimatedBuilder(
            animation: _bgAnimCtrl,
            builder: (_, _) => Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: [
                    Color.lerp(
                      const Color(0xFF0A1628),
                      const Color(0xFF0D1F3C),
                      _bgAnimCtrl.value,
                    )!,
                    Color.lerp(
                      const Color(0xFF0F2040),
                      const Color(0xFF1A1040),
                      _bgAnimCtrl.value,
                    )!,
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
                const NetworkBanner(),
                if (dashAsync.isLoading && dashAsync.valueOrNull == null)
                  Expanded(
                    child: SingleChildScrollView(
                      child: ShimmerLoader.homeSkeleton(),
                    ),
                  )
                else ...[
                  if (dashAsync.isLoading)
                    const LinearProgressIndicator(
                      minHeight: 2,
                      color: Color(0xFF00D4FF),
                      backgroundColor: Colors.transparent,
                    ),
                  Expanded(
                  child: RefreshIndicator(
                    color: const Color(0xFF00D4FF),
                    onRefresh: _onRefresh,
                    child: SingleChildScrollView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _buildTopBar(homeData),
                          if (_updateInfo != null &&
                              _updateInfo!['is_required'] != true) ...[
                            const SizedBox(height: 10),
                            _buildUpdateBanner(_updateInfo!),
                          ],
                          if (dashAsync.hasError) ...[
                            const SizedBox(height: 12),
                            _buildErrorBanner(
                                _userFriendlyError(dashAsync.error!)),
                          ],
                          const SizedBox(height: 20),
                          if (smartInsight != null) ...[
                            _buildSmartInsightCard(smartInsight)
                                .animate()
                                .fadeIn(duration: 350.ms)
                                .slideY(
                                    begin: 0.08,
                                    end: 0,
                                    duration: 350.ms),
                            const SizedBox(height: 14),
                          ],
                          _buildDanaGreetingCard()
                              .animate()
                              .fadeIn(duration: 400.ms)
                              .slideY(
                                  begin: 0.1, end: 0, duration: 400.ms),
                          const SizedBox(height: 16),
                          _buildSleepScoreCircle(
                                  homeData?.dashboard ?? {})
                              .animate()
                              .fadeIn(delay: 100.ms, duration: 400.ms)
                              .slideY(
                                  begin: 0.1,
                                  end: 0,
                                  delay: 100.ms,
                                  duration: 400.ms),
                          const SizedBox(height: 16),
                          _buildQuickStatsRow(homeData?.dashboard ?? {})
                              .animate()
                              .fadeIn(delay: 200.ms, duration: 400.ms)
                              .slideY(
                                  begin: 0.1,
                                  end: 0,
                                  delay: 200.ms,
                                  duration: 400.ms),
                          const SizedBox(height: 16),
                          const LiveSensorCard(),
                          if (activityFeed.isNotEmpty) ...[
                            const SizedBox(height: 16),
                            _buildDanaActivityFeed(activityFeed)
                                .animate()
                                .fadeIn(delay: 300.ms, duration: 400.ms),
                          ],
                          const SizedBox(height: 16),
                          _buildQuickActionsGrid()
                              .animate()
                              .fadeIn(delay: 350.ms, duration: 450.ms)
                              .slideY(
                                  begin: 0.08,
                                  end: 0,
                                  delay: 350.ms,
                                  duration: 450.ms),
                          const SizedBox(height: 20),
                          _buildIslamicSection(homeData?.dashboard ?? {})
                              .animate()
                              .fadeIn(delay: 450.ms, duration: 400.ms),
                        ],
                      ),
                    ),
                  ),
                ),
                ], // end else
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ─── Smart Insight Card ──────────────────────────────────────────────────

  Widget _buildSmartInsightCard(Map<String, dynamic> insight) {
    final String headline = insight['headline'] as String? ?? '';
    return GlassCard(
      borderRadius: 18,
      padding: const EdgeInsets.all(14),
      border:
          Border.all(color: AppColors.accent.withValues(alpha: 0.45), width: 1.5),
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
            child:
                const Icon(Icons.auto_awesome, color: AppColors.accent, size: 20),
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

  // ─── Dana Activity Feed ──────────────────────────────────────────────────

  Widget _buildDanaActivityFeed(List<Map<String, dynamic>> feed) {
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
            itemCount: feed.length,
            separatorBuilder: (_, _) => const SizedBox(width: 8),
            itemBuilder: (_, i) {
              final item = feed[i];
              final status = item['status'] as String? ?? 'info';
              final dotColor = _statusColor(status);
              final eventText = item['event'] as String? ?? '';
              final timeText = item['time'] as String? ?? '';
              return GlassCard(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
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
                            decoration: BoxDecoration(
                                color: dotColor, shape: BoxShape.circle),
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
                                    backgroundColor:
                                        const Color(0xFF0F2040),
                                    content: Text(
                                      eventText,
                                      style: const TextStyle(
                                          color: AppColors.softWhite,
                                          fontSize: 13),
                                    ),
                                    actions: [
                                      TextButton(
                                        onPressed: () =>
                                            Navigator.of(context).pop(),
                                        child: const Text('Close'),
                                      ),
                                    ],
                                  ),
                                )
                            : null,
                        child: Text(
                          eventText,
                          style: const TextStyle(
                              color: AppColors.softWhite,
                              fontSize: 11,
                              height: 1.4),
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

  // ─── Top Bar ─────────────────────────────────────────────────────────────

  Widget _buildTopBar(_HomeData? data) {
    final hour = DateTime.now().hour;
    final String greeting = hour < 12
        ? 'Good Morning'
        : hour < 18
            ? 'Good Afternoon'
            : 'Good Evening';
    final deviceOnline = data?.device['device_online'] == true;
    final userName = data?.userName ?? 'User';

    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    '$greeting, $userName',
                    style: const TextStyle(
                      color: AppColors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(width: 6),
                  const Icon(Icons.nightlight_round,
                      color: AppColors.softWhite, size: 18),
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
                          color: (deviceOnline ? Colors.green : Colors.red)
                              .withValues(alpha: 0.5),
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
        CachedAvatar(
          imageUrl: data?.profileImageUrl,
          initial: userName,
          radius: 20,
        ),
        const SizedBox(width: 10),
        GlassCard(
          padding: EdgeInsets.zero,
          borderRadius: 12,
          border:
              Border.all(color: AppColors.accent.withValues(alpha: 0.35)),
          child: IconButton(
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.nightlight_round,
                color: AppColors.softWhite),
            onPressed: () {},
            tooltip: 'Night settings',
          ),
        ),
      ],
    );
  }

  // ─── Dana Greeting Card ──────────────────────────────────────────────────

  Widget _buildDanaGreetingCard() {
    return GlassCard(
      borderRadius: 20,
      padding: const EdgeInsets.all(16),
      border:
          Border.all(color: AppColors.accent.withValues(alpha: 0.3)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.nightlight_round,
                  color: AppColors.accent, size: 18),
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
          Shimmer.fromColors(
            baseColor: AppColors.accent,
            highlightColor: Colors.white,
            child: const Text(
              'Dana Guide · Active',
              style:
                  TextStyle(fontSize: 13, fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }

  // ─── Sleep Score Circle ──────────────────────────────────────────────────

  Widget _buildSleepScoreCircle(Map<String, dynamic> dashboard) {
    final weeklyInsight = dashboard['weekly_insight'] ?? {};
    return AnimatedBuilder(
      animation: Listenable.merge([_scoreAnim, _bgAnimCtrl]),
      builder: (context, child) {
        final scoreColor = _scoreAnim.value > 0.7
            ? Colors.green
            : _scoreAnim.value > 0.5
                ? AppColors.accent
                : AppColors.orange;
        return GlassCard(
          borderRadius: 20,
          padding: const EdgeInsets.all(20),
          border: Border.all(
              color: AppColors.accent.withValues(alpha: 0.25)),
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
                    CustomPaint(
                      size: const Size(160, 160),
                      painter: _GlowRingPainter(
                        progress: _scoreAnim.value,
                        glowOpacity:
                            0.15 + (_bgAnimCtrl.value * 0.2),
                        color: scoreColor,
                      ),
                    ),
                    SizedBox(
                      width: 160,
                      height: 160,
                      child: CircularProgressIndicator(
                        value: _scoreAnim.value,
                        strokeWidth: 12,
                        backgroundColor:
                            AppColors.background.withValues(alpha: 0.6),
                        valueColor:
                            AlwaysStoppedAnimation<Color>(scoreColor),
                      ),
                    ),
                    Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          '${(_scoreAnim.value * 100).toInt()}',
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
                (weeklyInsight['summary'] as String?) ??
                    'Keep up the great work!',
                textAlign: TextAlign.center,
                style: const TextStyle(
                    color: AppColors.softWhite,
                    fontSize: 13,
                    height: 1.4),
              ),
            ],
          ),
        );
      },
    );
  }

  // ─── Quick Stats Row ─────────────────────────────────────────────────────

  Widget _buildQuickStatsRow(Map<String, dynamic> dashboard) {
    final weeklyInsight = dashboard['weekly_insight'] ?? {};
    final nightly = dashboard['nightly_summary'] ?? {};

    final String lastNight =
        (nightly['last_night_hours'] ?? '7.2h').toString();
    final String sleepScore =
        (weeklyInsight['completion_rate_pct'] ?? '82').toString();
    final String streak =
        (weeklyInsight['wind_down_sessions'] ?? '5').toString();

    return Row(
      children: [
        Expanded(
            child: _StatCard(
                label: 'Last Night',
                value: lastNight,
                accentColor: AppColors.accent)),
        const SizedBox(width: 10),
        Expanded(
            child: _StatCard(
                label: 'Sleep Score',
                value: sleepScore,
                accentColor: AppColors.purple)),
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

  // ─── Quick Actions Grid ──────────────────────────────────────────────────

  Widget _buildQuickActionsGrid() {
    final List<Widget> items = List.generate(_actions.length, (i) {
      final action = _actions[i];
      return AnimatedBuilder(
        animation: _staggerCtrl,
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
          onTap: () => context.push(action.route),
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

  // ─── Islamic Section ─────────────────────────────────────────────────────

  Widget _buildIslamicSection(Map<String, dynamic> dashboard) {
    final String nextPrayer =
        (dashboard['next_prayer'] ?? 'Isha').toString();
    final String prayerCountdown =
        (dashboard['next_prayer_eta'] ?? 'in 45 minutes').toString();

    return GlassCard(
      borderRadius: 18,
      padding: const EdgeInsets.all(16),
      border:
          Border.all(color: Colors.white.withValues(alpha: 0.12)),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: AppColors.accent.withValues(alpha: 0.1),
              shape: BoxShape.circle,
            ),
            child: const Icon(Icons.mosque_rounded,
                color: AppColors.softWhite, size: 20),
          ),
          const SizedBox(width: 14),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Next Prayer',
                style: TextStyle(
                    color: AppColors.softWhite,
                    fontSize: 12,
                    fontWeight: FontWeight.w500),
              ),
              const SizedBox(height: 2),
              Text(
                nextPrayer,
                style: const TextStyle(
                    color: AppColors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w700),
              ),
              Text(
                prayerCountdown,
                style: const TextStyle(
                    color: AppColors.accent,
                    fontSize: 13,
                    fontWeight: FontWeight.w600),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // ─── Banners ─────────────────────────────────────────────────────────────

  Widget _buildErrorBanner(String message) {
    return Container(
      padding:
          const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.orange.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
            color: AppColors.orange.withValues(alpha: 0.35)),
      ),
      child: Row(
        children: [
          const Icon(Icons.cloud_off_rounded,
              color: AppColors.orange, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(
                  color: AppColors.orange, fontSize: 12),
            ),
          ),
          TextButton(
            onPressed: _onRefresh,
            style: TextButton.styleFrom(
              foregroundColor: AppColors.orange,
              visualDensity: VisualDensity.compact,
              padding:
                  const EdgeInsets.symmetric(horizontal: 8),
            ),
            child: const Text('Retry',
                style: TextStyle(fontSize: 12)),
          ),
        ],
      ),
    );
  }

  Widget _buildUpdateBanner(Map<String, dynamic> info) {
    return Container(
      padding:
          const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
      decoration: BoxDecoration(
        color: const Color(0xFFC79A55).withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
            color: const Color(0xFFC79A55).withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          const Icon(Icons.system_update_rounded,
              color: Color(0xFFC79A55), size: 18),
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
                    style: const TextStyle(
                        color: Color(0xFF9B7A3A), fontSize: 11),
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
              padding:
                  const EdgeInsets.symmetric(horizontal: 8),
            ),
            child: const Text('Update',
                style: TextStyle(
                    fontSize: 12, fontWeight: FontWeight.w700)),
          ),
          IconButton(
            onPressed: () => setState(() => _updateInfo = null),
            icon: const Icon(Icons.close,
                size: 16, color: Color(0xFF9B7A3A)),
            visualDensity: VisualDensity.compact,
            padding: EdgeInsets.zero,
          ),
        ],
      ),
    );
  }
}

// ─── Glow Ring Painter ────────────────────────────────────────────────────────

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
      ..color = color.withValues(alpha: glowOpacity.clamp(0.0, 1.0))
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
      old.progress != progress ||
      old.glowOpacity != glowOpacity ||
      old.color != color;
}

// ─── Action Item Model ────────────────────────────────────────────────────────

class _ActionItem {
  const _ActionItem({
    required this.icon,
    required this.label,
    required this.color,
    required this.route,
  });
  final IconData icon;
  final String label;
  final Color color;
  final String route;
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

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
      padding:
          const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
      borderRadius: 14,
      border:
          Border.all(color: accentColor.withValues(alpha: 0.2)),
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

// ─── Quick Action Card ────────────────────────────────────────────────────────

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
    return Semantics(
      button: true,
      label: label,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: GlassCard(
            padding: const EdgeInsets.all(14),
            borderRadius: 16,
            border: Border.all(
                color: color.withValues(alpha: 0.35), width: 1.5),
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
      ),
    );
  }
}
