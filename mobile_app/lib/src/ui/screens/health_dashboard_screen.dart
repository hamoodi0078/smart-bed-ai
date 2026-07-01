import 'package:flutter/material.dart';
import '../theme.dart';

class HealthDashboardScreen extends StatefulWidget {
  const HealthDashboardScreen({super.key});

  @override
  State<HealthDashboardScreen> createState() => _HealthDashboardScreenState();
}

class _HealthDashboardScreenState extends State<HealthDashboardScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  int _waterGlasses = 4;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: SmartBedPalette.background,
      appBar: AppBar(
        backgroundColor: SmartBedPalette.background,
        foregroundColor: Colors.white,
        elevation: 0,
        title: const Text(
          'Health Dashboard',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: SmartBedPalette.accent,
          labelColor: SmartBedPalette.accent,
          unselectedLabelColor: Colors.white70,
          tabs: const <Tab>[
            Tab(text: 'Overview'),
            Tab(text: 'Sleep'),
            Tab(text: 'Wellness'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: <Widget>[
          _buildOverviewTab(),
          _buildSleepTab(),
          _buildWellnessTab(),
        ],
      ),
    );
  }

  Widget _buildOverviewTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _buildHealthScoreCard(),
          const SizedBox(height: 16),
          _buildVitalStatsRow(),
          const SizedBox(height: 16),
          _buildWeeklyTrendCard(),
          const SizedBox(height: 16),
          _buildHydrationCard(),
        ],
      ),
    );
  }

  Widget _buildSleepTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _buildSleepStagesCard(),
          const SizedBox(height: 16),
          _buildSleepTimelineCard(),
          const SizedBox(height: 16),
          _buildSleepInsightsCard(),
        ],
      ),
    );
  }

  Widget _buildWellnessTab() {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          _buildStressCard(),
          const SizedBox(height: 16),
          _buildPrayerHealthCard(),
          const SizedBox(height: 16),
          _buildTipsCard(),
        ],
      ),
    );
  }

  Widget _buildHealthScoreCard() {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: <Color>[
            SmartBedPalette.surface(theme.brightness),
            const Color(0xFF1A2640),
          ],
        ),
        border: Border.all(color: SmartBedPalette.accent.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: <Widget>[
          SizedBox(
            width: 90,
            height: 90,
            child: Stack(
              alignment: Alignment.center,
              children: <Widget>[
                CircularProgressIndicator(
                  value: 0.78,
                  strokeWidth: 8,
                  backgroundColor: SmartBedPalette.surfaceAlt(theme.brightness),
                  valueColor: const AlwaysStoppedAnimation<Color>(Colors.green),
                ),
                const Column(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text(
                      '78',
                      style: TextStyle(
                        color: Colors.green,
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text(
                      'Health',
                      style: TextStyle(
                        color: Colors.white70,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(width: 20),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                const Text(
                  'Overall Health Score',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  'Good — Keep up your sleep routine and hydration.',
                  style: TextStyle(
                    color: SmartBedPalette.body(theme.brightness),
                    fontSize: 13,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 10),
                _buildScoreBadge('+3 from last week', Colors.green),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildScoreBadge(String text, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Widget _buildVitalStatsRow() {
    return Row(
      children: <Widget>[
        const Expanded(
          child: _VitalCard(
            icon: Icons.bedtime_rounded,
            label: 'Avg Sleep',
            value: '7.2h',
            color: SmartBedPalette.accent,
          ),
        ),
        const SizedBox(width: 10),
        const Expanded(
          child: _VitalCard(
            icon: Icons.water_drop_rounded,
            label: 'Hydration',
            value: '60%',
            color: Color(0xFF4FC3F7),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: _VitalCard(
            icon: Icons.local_fire_department_rounded,
            label: 'Streak',
            value: '5d',
            color: SmartBedPalette.warmAccent,
          ),
        ),
      ],
    );
  }

  Widget _buildWeeklyTrendCard() {
    final theme = Theme.of(context);
    const days = <String>['M', 'T', 'W', 'T', 'F', 'S', 'S'];
    const hours = <double>[6.5, 7.0, 7.5, 6.0, 8.0, 7.2, 7.8];
    final maxHours = hours.reduce((a, b) => a > b ? a : b);

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SmartBedPalette.surface(theme.brightness),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: SmartBedPalette.accent.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Sleep This Week',
            style: TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 20),
          SizedBox(
            height: 100,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: List<Widget>.generate(days.length, (i) {
                final barHeight = (hours[i] / maxHours) * 80;
                final isToday = i == 3;
                return Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: <Widget>[
                      Container(
                        height: barHeight,
                        margin: const EdgeInsets.symmetric(horizontal: 3),
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(6),
                          color: isToday
                              ? SmartBedPalette.accent
                              : SmartBedPalette.accent.withValues(alpha: 0.35),
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        days[i],
                        style: TextStyle(
                          color: isToday
                              ? SmartBedPalette.accent
                              : SmartBedPalette.body(theme.brightness).withValues(alpha: 0.6),
                          fontSize: 11,
                          fontWeight:
                              isToday ? FontWeight.w700 : FontWeight.w400,
                        ),
                      ),
                    ],
                  ),
                );
              }),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHydrationCard() {
    final theme = Theme.of(context);
    const goal = 8;
    final percent = _waterGlasses / goal;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SmartBedPalette.surface(theme.brightness),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: const Color(0xFF4FC3F7).withValues(alpha: 0.3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              const Icon(
                Icons.water_drop_rounded,
                color: Color(0xFF4FC3F7),
                size: 20,
              ),
              const SizedBox(width: 8),
              const Expanded(
                child: Text(
                  'Hydration Today',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              Text(
                '$_waterGlasses / $goal glasses',
                style: const TextStyle(
                  color: Color(0xFF4FC3F7),
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: LinearProgressIndicator(
              value: percent,
              minHeight: 10,
              backgroundColor: SmartBedPalette.background,
              valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF4FC3F7)),
            ),
          ),
          const SizedBox(height: 16),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: List<Widget>.generate(goal, (i) {
              return GestureDetector(
                onTap: () => setState(() => _waterGlasses = i + 1),
                child: Icon(
                  Icons.water_drop_rounded,
                  size: 28,
                  color: i < _waterGlasses
                      ? const Color(0xFF4FC3F7)
                      : SmartBedPalette.body(theme.brightness).withValues(alpha: 0.2),
                ),
              );
            }),
          ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () {
                if (_waterGlasses < goal) {
                  setState(() => _waterGlasses++);
                }
              },
              style: OutlinedButton.styleFrom(
                foregroundColor: const Color(0xFF4FC3F7),
                side: const BorderSide(color: Color(0xFF4FC3F7)),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              icon: const Icon(Icons.add_rounded),
              label: const Text('Log a Glass'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSleepStagesCard() {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SmartBedPalette.surface(theme.brightness),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: SmartBedPalette.secondaryAccent.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Sleep Stages — Last Night',
            style: TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 20),
          _buildStageBar('Deep Sleep', 0.22, SmartBedPalette.secondaryAccent, '1h 38m'),
          const SizedBox(height: 12),
          _buildStageBar('Light Sleep', 0.45, SmartBedPalette.accent, '3h 22m'),
          const SizedBox(height: 12),
          _buildStageBar('REM Sleep', 0.20, SmartBedPalette.warmAccent, '1h 30m'),
          const SizedBox(height: 12),
          _buildStageBar('Awake', 0.13, Colors.white60, '0h 58m'),
        ],
      ),
    );
  }

  Widget _buildStageBar(String label, double value, Color color, String time) {
    final theme = Theme.of(context);
    return Row(
      children: <Widget>[
        SizedBox(
          width: 90,
          child: Text(
            label,
            style: TextStyle(
              color: SmartBedPalette.body(theme.brightness),
              fontSize: 13,
            ),
          ),
        ),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(6),
            child: LinearProgressIndicator(
              value: value,
              minHeight: 10,
              backgroundColor: SmartBedPalette.background,
              valueColor: AlwaysStoppedAnimation<Color>(color),
            ),
          ),
        ),
        const SizedBox(width: 10),
        SizedBox(
          width: 48,
          child: Text(
            time,
            textAlign: TextAlign.right,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildSleepTimelineCard() {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SmartBedPalette.surface(theme.brightness),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: SmartBedPalette.accent.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Text(
            'Sleep Timeline',
            style: TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 16),
          _buildTimelineRow(Icons.bedtime_rounded, 'Bedtime', '10:45 PM', SmartBedPalette.secondaryAccent),
          _buildTimelineRow(Icons.nightlight_rounded, 'Fell Asleep', '11:12 PM', SmartBedPalette.accent),
          _buildTimelineRow(Icons.wb_sunny_rounded, 'Wake Up', '6:34 AM', SmartBedPalette.warmAccent),
          _buildTimelineRow(Icons.timer_rounded, 'Total Sleep', '7h 22m', Colors.green),
        ],
      ),
    );
  }

  Widget _buildTimelineRow(IconData icon, String label, String value, Color color) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        children: <Widget>[
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: color, size: 18),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                color: SmartBedPalette.body(theme.brightness),
                fontSize: 14,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSleepInsightsCard() {
    final theme = Theme.of(context);
    final insights = <_Insight>[
      const _Insight('Your deep sleep improved by 8% this week', Icons.trending_up_rounded, Colors.green),
      const _Insight('Wind-down sessions correlate with better REM sleep', Icons.nightlight_round, SmartBedPalette.accent),
      const _Insight('Try sleeping 30 min earlier for optimal rest', Icons.tips_and_updates_rounded, SmartBedPalette.gold),
    ];

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SmartBedPalette.surface(theme.brightness),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: SmartBedPalette.gold.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Row(
            children: <Widget>[
              Icon(Icons.tips_and_updates_rounded, color: SmartBedPalette.gold, size: 18),
              SizedBox(width: 8),
              Text(
                'Sleep Insights',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          ...insights.map(
            (insight) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Icon(insight.icon, color: insight.color, size: 18),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      insight.text,
                      style: TextStyle(
                        color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.85),
                        fontSize: 13,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStressCard() {
    final theme = Theme.of(context);
    const levels = <int>[2, 4, 3, 5, 2, 3, 2];
    const daysLabel = <String>['M', 'T', 'W', 'T', 'F', 'S', 'S'];

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SmartBedPalette.surface(theme.brightness),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: SmartBedPalette.warmAccent.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Row(
            children: <Widget>[
              Icon(Icons.psychology_rounded, color: SmartBedPalette.warmAccent, size: 20),
              SizedBox(width: 8),
              Text(
                'Stress Levels',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          const Text(
            'Lower is better (1–5 scale)',
            style: TextStyle(color: Colors.white70, fontSize: 12),
          ),
          const SizedBox(height: 20),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: List<Widget>.generate(levels.length, (i) {
              final barH = (levels[i] / 5) * 60.0;
              final color = levels[i] <= 2
                  ? Colors.green
                  : levels[i] <= 3
                      ? SmartBedPalette.gold
                      : SmartBedPalette.warmAccent;
              return Expanded(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: <Widget>[
                    Container(
                      height: barH,
                      margin: const EdgeInsets.symmetric(horizontal: 3),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(6),
                        color: color,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      daysLabel[i],
                      style: TextStyle(
                        color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.6),
                        fontSize: 11,
                      ),
                    ),
                  ],
                ),
              );
            }),
          ),
        ],
      ),
    );
  }

  Widget _buildPrayerHealthCard() {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SmartBedPalette.surface(theme.brightness),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.green.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Row(
            children: <Widget>[
              Icon(Icons.mosque_rounded, color: Colors.green, size: 20),
              SizedBox(width: 8),
              Text(
                'Prayer & Health',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _buildPrayerStatRow('Prayers on time this week', '28 / 35', Colors.green),
          _buildPrayerStatRow('Sleep aligned with Isha', '5 / 7 nights', SmartBedPalette.accent),
          _buildPrayerStatRow('Fajr wake-up rate', '71%', SmartBedPalette.gold),
        ],
      ),
    );
  }

  Widget _buildPrayerStatRow(String label, String value, Color color) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                color: Colors.white70,
                fontSize: 13,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 14,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTipsCard() {
    final theme = Theme.of(context);
    const tips = <String>[
      'Consistent prayer times create a natural circadian rhythm.',
      'Drinking water before Fajr helps boost morning energy.',
      'Brief stretching after each prayer reduces cortisol.',
    ];

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: SmartBedPalette.surface(theme.brightness),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: SmartBedPalette.accent.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Row(
            children: <Widget>[
              Icon(Icons.lightbulb_outline_rounded, color: SmartBedPalette.accent, size: 18),
              SizedBox(width: 8),
              Text(
                'Wellness Tips',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          ...tips.asMap().entries.map(
            (entry) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Container(
                    width: 22,
                    height: 22,
                    decoration: BoxDecoration(
                      color: SmartBedPalette.accent.withValues(alpha: 0.15),
                      shape: BoxShape.circle,
                    ),
                    child: Center(
                      child: Text(
                        '${entry.key + 1}',
                        style: const TextStyle(
                          color: SmartBedPalette.accent,
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      entry.value,
                      style: TextStyle(
                        color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.85),
                        fontSize: 13,
                        height: 1.4,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _VitalCard extends StatelessWidget {
  const _VitalCard({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  final IconData icon;
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 14),
      decoration: BoxDecoration(
        color: SmartBedPalette.surface(theme.brightness),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(
        children: <Widget>[
          Icon(icon, color: color, size: 22),
          const SizedBox(height: 6),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 18,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: TextStyle(
              color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.65),
              fontSize: 11,
            ),
          ),
        ],
      ),
    );
  }
}

class _Insight {
  const _Insight(this.text, this.icon, this.color);
  final String text;
  final IconData icon;
  final Color color;
}
