import 'package:flutter/material.dart';
import '../theme.dart';

class SleepTipsScreen extends StatefulWidget {
  const SleepTipsScreen({super.key});

  @override
  State<SleepTipsScreen> createState() => _SleepTipsScreenState();
}

class _SleepTipsScreenState extends State<SleepTipsScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  static const List<_SleepTip> _allTips = <_SleepTip>[
    _SleepTip(
      id: '1',
      category: 'Routine',
      title: 'Consistent Sleep Schedule',
      description: 'Go to bed and wake up at the same time every day, even on weekends. This helps regulate your body\'s internal clock.',
      icon: Icons.access_time_rounded,
      color: SmartBedPalette.secondaryAccent,
      isNew: true,
    ),
    _SleepTip(
      id: '2',
      category: 'Environment',
      title: 'Optimal Bedroom Temperature',
      description: 'Keep your bedroom between 60-67°F (15-19°C). A cooler room promotes better sleep quality.',
      icon: Icons.thermostat_rounded,
      color: SmartBedPalette.accent,
      isNew: false,
    ),
    _SleepTip(
      id: '3',
      category: 'Diet',
      title: 'Avoid Caffeine After 2 PM',
      description: 'Caffeine can stay in your system for 6-8 hours. Avoid coffee, tea, and energy drinks in the afternoon.',
      icon: Icons.local_cafe_rounded,
      color: SmartBedPalette.warmAccent,
      isNew: true,
    ),
    _SleepTip(
      id: '4',
      category: 'Environment',
      title: 'Darkness is Essential',
      description: 'Use blackout curtains or an eye mask. Light exposure suppresses melatonin production.',
      icon: Icons.nightlight_round,
      color: SmartBedPalette.secondaryAccent,
      isNew: false,
    ),
    _SleepTip(
      id: '5',
      category: 'Routine',
      title: 'Wind-Down Ritual',
      description: 'Create a 30-60 minute pre-sleep routine. Try reading, stretching, or meditation.',
      icon: Icons.self_improvement_rounded,
      color: SmartBedPalette.accent,
      isNew: false,
    ),
    _SleepTip(
      id: '6',
      category: 'Technology',
      title: 'Limit Screen Time',
      description: 'Avoid screens 1 hour before bed. Blue light disrupts your natural sleep-wake cycle.',
      icon: Icons.smartphone_rounded,
      color: SmartBedPalette.warmAccent,
      isNew: true,
    ),
    _SleepTip(
      id: '7',
      category: 'Diet',
      title: 'Light Evening Meals',
      description: 'Eat dinner 2-3 hours before bed. Heavy meals can cause discomfort and disrupt sleep.',
      icon: Icons.restaurant_rounded,
      color: SmartBedPalette.gold,
      isNew: false,
    ),
    _SleepTip(
      id: '8',
      category: 'Exercise',
      title: 'Regular Physical Activity',
      description: 'Exercise regularly, but not within 3 hours of bedtime. Morning workouts are ideal.',
      icon: Icons.fitness_center_rounded,
      color: Colors.green,
      isNew: false,
    ),
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 5, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  List<_SleepTip> _getTipsForCategory(String category) {
    if (category == 'All') return _allTips;
    return _allTips.where((tip) => tip.category == category).toList();
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
          'Sleep Tips',
          style: TextStyle(fontWeight: FontWeight.w700),
        ),
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          indicatorColor: SmartBedPalette.accent,
          labelColor: SmartBedPalette.accent,
          unselectedLabelColor: Colors.white70,
          tabs: const <Tab>[
            Tab(text: 'All'),
            Tab(text: 'Routine'),
            Tab(text: 'Environment'),
            Tab(text: 'Diet'),
            Tab(text: 'Exercise'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: <Widget>[
          _buildTipsList('All'),
          _buildTipsList('Routine'),
          _buildTipsList('Environment'),
          _buildTipsList('Diet'),
          _buildTipsList('Exercise'),
        ],
      ),
    );
  }

  Widget _buildTipsList(String category) {
    final tips = _getTipsForCategory(category);
    
    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: tips.length,
      itemBuilder: (context, index) {
        return _TipCard(tip: tips[index]);
      },
    );
  }
}

class _TipCard extends StatelessWidget {
  const _TipCard({required this.tip});

  final _SleepTip tip;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(16),
        color: SmartBedPalette.surface(theme.brightness),
        border: Border.all(
          color: tip.color.withValues(alpha: 0.3),
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: () {
            _showTipDetail(context, tip);
          },
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: tip.color.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    tip.icon,
                    color: tip.color,
                    size: 28,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Row(
                        children: <Widget>[
                          Expanded(
                            child: Text(
                              tip.title,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                          ),
                          if (tip.isNew)
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 4,
                              ),
                              decoration: BoxDecoration(
                                color: SmartBedPalette.accent.withValues(alpha: 0.2),
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(
                                  color: SmartBedPalette.accent,
                                ),
                              ),
                              child: const Text(
                                'NEW',
                                style: TextStyle(
                                  color: SmartBedPalette.accent,
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text(
                        tip.category,
                        style: TextStyle(
                          color: tip.color.withValues(alpha: 0.8),
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        tip.description,
                        style: TextStyle(
                          color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.8),
                          fontSize: 14,
                          height: 1.4,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),
                Icon(
                  Icons.chevron_right_rounded,
                  color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.4),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  static void _showTipDetail(BuildContext context, _SleepTip tip) {
    final theme = Theme.of(context);
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => Container(
        height: MediaQuery.of(context).size.height * 0.7,
        decoration: BoxDecoration(
          color: SmartBedPalette.background,
          borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        ),
        child: Column(
          children: <Widget>[
            Container(
              margin: const EdgeInsets.symmetric(vertical: 12),
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.3),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: tip.color.withValues(alpha: 0.2),
                        shape: BoxShape.circle,
                      ),
                      child: Icon(
                        tip.icon,
                        color: tip.color,
                        size: 48,
                      ),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      tip.title,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 24,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: tip.color.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        tip.category,
                        style: TextStyle(
                          color: tip.color,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    const SizedBox(height: 20),
                    Text(
                      tip.description,
                      style: TextStyle(
                        color: SmartBedPalette.body(theme.brightness).withValues(alpha: 0.9),
                        fontSize: 16,
                        height: 1.6,
                      ),
                    ),
                    const SizedBox(height: 24),
                    _buildActionButtons(context, tip),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static Widget _buildActionButtons(BuildContext context, _SleepTip tip) {
    return Column(
      children: <Widget>[
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: () {
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Tip saved to your favorites!'),
                  backgroundColor: SmartBedPalette.accent,
                ),
              );
            },
            style: FilledButton.styleFrom(
              backgroundColor: tip.color,
              foregroundColor: SmartBedPalette.background,
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
            icon: const Icon(Icons.bookmark_add_rounded),
            label: const Text('Save Tip'),
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            onPressed: () {
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Reminder set for tonight!'),
                  backgroundColor: SmartBedPalette.secondaryAccent,
                ),
              );
            },
            style: OutlinedButton.styleFrom(
              foregroundColor: tip.color,
              side: BorderSide(color: tip.color),
              padding: const EdgeInsets.symmetric(vertical: 14),
            ),
            icon: const Icon(Icons.notifications_rounded),
            label: const Text('Set Reminder'),
          ),
        ),
      ],
    );
  }
}

class _SleepTip {
  const _SleepTip({
    required this.id,
    required this.category,
    required this.title,
    required this.description,
    required this.icon,
    required this.color,
    required this.isNew,
  });

  final String id;
  final String category;
  final String title;
  final String description;
  final IconData icon;
  final Color color;
  final bool isNew;
}
