import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:lottie/lottie.dart';

import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../home/home_screen.dart';

class SleepReportScreen extends StatefulWidget {
  const SleepReportScreen({super.key});

  @override
  State<SleepReportScreen> createState() => _SleepReportScreenState();
}

class _SleepReportScreenState extends State<SleepReportScreen> {
  bool _isLoading = true;
  String? _errorMessage;

  int _weeklyScore = 0;
  String _weeklyScoreLabel = '—';
  String _avgSleep = '—';
  String _nightsTracked = '—';
  String _bestNight = '—';
  String _bestNightHours = '—';
  String _worstNight = '—';
  String _worstNightHours = '—';
  String _danaSummary = '';
  String _streak = '0';

  List<_SleepBarPoint> _weeklyData = const [
    _SleepBarPoint(day: 'Mon', hours: 0),
    _SleepBarPoint(day: 'Tue', hours: 0),
    _SleepBarPoint(day: 'Wed', hours: 0),
    _SleepBarPoint(day: 'Thu', hours: 0),
    _SleepBarPoint(day: 'Fri', hours: 0),
    _SleepBarPoint(day: 'Sat', hours: 0),
    _SleepBarPoint(day: 'Sun', hours: 0),
  ];

  @override
  void initState() {
    super.initState();
    _loadReport();
  }

  Future<void> _loadReport() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final data = await ApiService.getDashboard();
      if (data['error'] == true) throw Exception(data['message']);

      final weekly = data['weekly_insight'] as Map<String, dynamic>? ?? {};
      final nightly = data['nightly_summary'] as Map<String, dynamic>? ?? {};

      final score = (weekly['completion_rate_pct'] ?? 0) as num;
      final avgHours = (nightly['avg_hours'] ?? nightly['last_night_hours'] ?? 0) as num;
      final sessions = (weekly['wind_down_sessions'] ?? 0) as num;
      final summary = weekly['summary'] as String? ?? '';

      // Build bar chart from weekly_hours_breakdown if available
      final breakdown = weekly['weekly_hours_breakdown'];
      final List<_SleepBarPoint> bars;
      if (breakdown is Map) {
        final dayOrder = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
        bars = dayOrder
            .map((d) => _SleepBarPoint(
                  day: d,
                  hours: ((breakdown[d] ?? breakdown[d.toLowerCase()] ?? 0) as num).toDouble(),
                ))
            .toList();
      } else {
        bars = _weeklyData;
      }

      // Derive best/worst from bar data
      final sorted = [...bars]..sort((a, b) => b.hours.compareTo(a.hours));
      final best = sorted.isNotEmpty ? sorted.first : null;
      final worst = sorted.isNotEmpty ? sorted.last : null;

      final String scoreLabel;
      if (score >= 80) {
        scoreLabel = 'Great';
      } else if (score >= 60) {
        scoreLabel = 'Good';
      } else {
        scoreLabel = 'Needs Work';
      }

      if (mounted) {
        setState(() {
          _weeklyScore = score.toInt();
          _weeklyScoreLabel = scoreLabel;
          _avgSleep = avgHours > 0 ? '${avgHours.toStringAsFixed(1)}h' : '—';
          _nightsTracked = sessions > 0 ? '$sessions/7' : '—';
          _bestNight = best?.day ?? '—';
          _bestNightHours = best != null && best.hours > 0
              ? '${best.hours.toStringAsFixed(1)} hours'
              : '—';
          _worstNight = worst?.day ?? '—';
          _worstNightHours = worst != null && worst.hours > 0
              ? '${worst.hours.toStringAsFixed(1)} hours'
              : '—';
          _danaSummary = summary;
          _streak = sessions.toString();
          _weeklyData = bars;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _errorMessage = e.toString().replaceAll('Exception: ', '');
          _isLoading = false;
        });
      }
    }
  }

  void _goBack() {
    if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
      return;
    }
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const HomeScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: SafeArea(
        child: Column(
          children: [
            if (_isLoading)
              Lottie.asset(
                'assets/animations/loading_moon.json',
                width: 72,
                height: 4,
                fit: BoxFit.fitWidth,
                errorBuilder: (_, _, _) => const LinearProgressIndicator(
                  minHeight: 2,
                  color: Color(0xFF00D4FF),
                  backgroundColor: Colors.transparent,
                ),
              ),
            Expanded(
              child: RefreshIndicator(
                color: const Color(0xFF00D4FF),
                onRefresh: _loadReport,
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildTopBar(),
                      if (_errorMessage != null) ...[
                        const SizedBox(height: 10),
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 12, vertical: 10),
                          decoration: BoxDecoration(
                            color: AppColors.orange.withValues(alpha: 0.15),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                                color: AppColors.orange.withValues(alpha: 0.4)),
                          ),
                          child: Row(
                            children: [
                              const Icon(Icons.wifi_off_rounded,
                                  color: AppColors.orange, size: 16),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  'Could not load report — $_errorMessage',
                                  style: const TextStyle(
                                      color: AppColors.orange, fontSize: 12),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                      const SizedBox(height: 14),
                      _buildWeeklyScoreSection(),
                      const SizedBox(height: 14),
                      _buildBarChartSection(),
                      const SizedBox(height: 14),
                      _buildBestWorstSection(),
                      const SizedBox(height: 14),
                      _buildDanaSummaryCard(),
                      const SizedBox(height: 14),
                      _buildStreakCard(),
                    ],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _weekRangeLabel() {
    final now = DateTime.now();
    final weekday = now.weekday; // Mon=1, Sun=7
    final start = now.subtract(Duration(days: weekday - 1));
    final end = start.add(const Duration(days: 6));
    final fmt = DateFormat('MMM d');
    return '${fmt.format(start)} – ${fmt.format(end)}';
  }

  Widget _buildTopBar() {
    return Row(
      children: [
        IconButton(
          onPressed: _goBack,
          icon: const Icon(Icons.arrow_back_ios_new_rounded),
          color: AppColors.white,
          tooltip: 'Back',
        ),
        const Expanded(
          child: Text(
            '📊 Sleep Report',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.white,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        SizedBox(
          width: 72,
          child: Text(
            _weekRangeLabel(),
            textAlign: TextAlign.right,
            style: const TextStyle(
              color: AppColors.accent,
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildWeeklyScoreSection() {
    return Column(
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 16),
          decoration: BoxDecoration(
            color: const Color(0xFF1A2640),
            borderRadius: BorderRadius.circular(22),
            border: Border.all(
              color: AppColors.accent.withValues(alpha: 0.65),
              width: 1.2,
            ),
            boxShadow: [
              BoxShadow(
                color: AppColors.accent.withValues(alpha: 0.3),
                blurRadius: 20,
                spreadRadius: 0.8,
              ),
            ],
          ),
          child: Column(
            children: [
              Text(
                '$_weeklyScore',
                style: const TextStyle(
                  color: AppColors.accent,
                  fontSize: 64,
                  fontWeight: FontWeight.w700,
                  height: 1,
                ),
              ),
              const Text(
                '/ 100',
                style: TextStyle(
                  color: AppColors.softWhite,
                  fontSize: 20,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                _weeklyScoreLabel,
                style: const TextStyle(
                  color: AppColors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const SizedBox(height: 4),
              const Text(
                'Weekly Average Score',
                style: TextStyle(
                  color: Color(0xFF9CA6BF),
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
                decoration: BoxDecoration(
                  color: AppColors.cardBg,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Avg Sleep',
                      style: TextStyle(
                        color: Color(0xFF9CA6BF),
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      _avgSleep,
                      style: const TextStyle(
                        color: AppColors.accent,
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
                decoration: BoxDecoration(
                  color: AppColors.cardBg,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Nights Tracked',
                      style: TextStyle(
                        color: Color(0xFF9CA6BF),
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      _nightsTracked,
                      style: const TextStyle(
                        color: AppColors.accent,
                        fontSize: 18,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildBarChartSection() {
    final maxHours = _weeklyData.fold<double>(
        9, (m, p) => p.hours.toDouble() > m ? p.hours.toDouble() : m);
    final bestDay =
        _weeklyData.reduce((a, b) => a.hours >= b.hours ? a : b).day;

    final barGroups = List.generate(_weeklyData.length, (i) {
      final point = _weeklyData[i];
      final isBest = point.day == bestDay;
      return BarChartGroupData(
        x: i,
        barRods: [
          BarChartRodData(
            toY: point.hours.toDouble(),
            color: isBest ? AppColors.gold : AppColors.accent,
            width: 18,
            borderRadius: BorderRadius.circular(6),
          ),
        ],
      );
    });

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 14, 14, 12),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'This Week',
            style: TextStyle(
              color: AppColors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 160,
            child: BarChart(
              BarChartData(
                maxY: maxHours + 1,
                barGroups: barGroups,
                gridData: FlGridData(
                  show: true,
                  drawVerticalLine: false,
                  horizontalInterval: 2,
                  getDrawingHorizontalLine: (_) => const FlLine(
                    color: Colors.white10,
                    strokeWidth: 1,
                  ),
                ),
                borderData: FlBorderData(show: false),
                titlesData: FlTitlesData(
                  leftTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                  bottomTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      getTitlesWidget: (value, _) {
                        final idx = value.toInt();
                        if (idx < 0 || idx >= _weeklyData.length) {
                          return const SizedBox.shrink();
                        }
                        return Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            _weeklyData[idx].day,
                            style: const TextStyle(
                                color: AppColors.white, fontSize: 10),
                          ),
                        );
                      },
                    ),
                  ),
                ),
                barTouchData: BarTouchData(
                  touchTooltipData: BarTouchTooltipData(
                    getTooltipColor: (_) => const Color(0xFF1E2D45),
                    getTooltipItem: (group, _, rod, _) => BarTooltipItem(
                      '${rod.toY.toStringAsFixed(1)}h',
                      const TextStyle(color: AppColors.white, fontSize: 11),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBestWorstSection() {
    return Row(
      children: [
        Expanded(
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.cardBg,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '🏆 Best Night',
                  style: TextStyle(
                    color: AppColors.gold,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _bestNight,
                  style: const TextStyle(
                    color: AppColors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  _bestNightHours,
                  style: const TextStyle(
                    color: AppColors.accent,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.cardBg,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '😴 Needs Work',
                  style: TextStyle(
                    color: AppColors.orange,
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _worstNight,
                  style: const TextStyle(
                    color: AppColors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  _worstNightHours,
                  style: const TextStyle(
                    color: AppColors.orange,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildDanaSummaryCard() {
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
            "🌙 Dana's Insight",
            style: TextStyle(
              color: AppColors.white,
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            _danaSummary.isNotEmpty
                ? _danaSummary
                : 'Keep your routine consistent for better sleep!',
            style: const TextStyle(
              color: AppColors.softWhite,
              fontSize: 12,
              fontStyle: FontStyle.italic,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStreakCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 16),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        children: [
          Text(
            '🔥 Current Streak: $_streak nights',
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.orange,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Keep going! Great work on your sleep routine 🏆',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.softWhite,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}

class _SleepBarPoint {
  const _SleepBarPoint({
    required this.day,
    required this.hours,
  });

  final String day;
  final double hours;
}
