import 'package:flutter/material.dart';

import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../home/home_screen.dart';

// Helper: returns TextDirection.rtl when text contains Arabic characters.
TextDirection _detectDirection(String text) {
  return RegExp(r'[\u0600-\u06FF]').hasMatch(text)
      ? TextDirection.rtl
      : TextDirection.ltr;
}

class IslamicScreen extends StatefulWidget {
  const IslamicScreen({super.key});

  @override
  State<IslamicScreen> createState() => _IslamicScreenState();
}

class _IslamicScreenState extends State<IslamicScreen> {
  bool _islamicModeEnabled = true;
  bool _isLoading = true;
  String? _errorMessage;

  List<Map<String, String>> _prayerTimes = const [
    {'name': 'Fajr', 'time': '--:--'},
    {'name': 'Dhuhr', 'time': '--:--'},
    {'name': 'Asr', 'time': '--:--'},
    {'name': 'Maghrib', 'time': '--:--'},
    {'name': 'Isha', 'time': '--:--'},
  ];
  int _nextPrayerIndex = 0;
  String _nextPrayerName = '';
  String _nextPrayerEta = '';
  bool _isRamadan = false;
  String _hijriDate = '';
  String _hadith = '';
  String _hadithSource = '';

  @override
  void initState() {
    super.initState();
    _loadIslamicData();
  }

  Future<void> _loadIslamicData() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });
    try {
      final data = await ApiService.getIslamicOverview();
      if (data['error'] == true) throw Exception(data['message']);

      final times = data['prayer_times'];
      if (times is Map) {
        final List<Map<String, String>> parsed = [];
        final order = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha'];
        for (final name in order) {
          parsed.add({'name': name, 'time': times[name.toLowerCase()] ?? times[name] ?? '--:--'});
        }
        final nextPrayer = data['next_prayer'] as String? ?? '';
        final nextIdx = order.indexWhere(
          (n) => n.toLowerCase() == nextPrayer.toLowerCase(),
        );
        if (mounted) {
          setState(() {
            _prayerTimes = parsed;
            _nextPrayerIndex = nextIdx < 0 ? 0 : nextIdx;
            _nextPrayerName = nextPrayer;
            _nextPrayerEta = data['next_prayer_eta'] as String? ?? '';
            _isRamadan = data['is_ramadan'] as bool? ?? false;
            _hijriDate = data['hijri_date'] as String? ?? '';
            _hadith = data['hadith'] as String? ?? '';
            _hadithSource = data['hadith_source'] as String? ?? '';
            _isLoading = false;
          });
        }
      } else {
        if (mounted) setState(() => _isLoading = false);
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
              const LinearProgressIndicator(
                minHeight: 2,
                color: Color(0xFF00D4FF),
                backgroundColor: Colors.transparent,
              ),
            Expanded(
              child: RefreshIndicator(
                color: const Color(0xFF00D4FF),
                onRefresh: _loadIslamicData,
                child: SingleChildScrollView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _buildTopBar(),
                      if (_errorMessage != null) ...[
                        const SizedBox(height: 12),
                        _buildErrorBanner(),
                      ],
                      const SizedBox(height: 14),
                      _buildPrayerTimesCard(),
                      const SizedBox(height: 14),
                      _buildNextPrayerCard(),
                      const SizedBox(height: 14),
                      _buildHadithCard(),
                      const SizedBox(height: 14),
                      _buildHijriCard(),
                      const SizedBox(height: 14),
                      _buildSunnahTipCard(),
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

  Widget _buildErrorBanner() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.orange.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.orange.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          const Icon(Icons.wifi_off_rounded, color: AppColors.orange, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Showing cached data — $_errorMessage',
              style: const TextStyle(color: AppColors.orange, fontSize: 12),
            ),
          ),
          IconButton(
            onPressed: _loadIslamicData,
            icon: const Icon(Icons.refresh_rounded, color: AppColors.orange, size: 18),
            visualDensity: VisualDensity.compact,
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(),
          ),
        ],
      ),
    );
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
            '🕌 Islamic Mode',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.white,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        Container(
          width: 56,
          height: 32,
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            boxShadow: _islamicModeEnabled
                ? [
                    BoxShadow(
                      color: AppColors.accent.withValues(alpha: 0.45),
                      blurRadius: 12,
                      spreadRadius: 0.8,
                    ),
                  ]
                : [],
          ),
          child: FittedBox(
            fit: BoxFit.contain,
            child: Switch(
              value: _islamicModeEnabled,
              activeThumbColor: AppColors.accent,
              activeTrackColor: AppColors.accent.withValues(alpha: 0.4),
              inactiveThumbColor: const Color(0xFFB0B0B0),
              inactiveTrackColor: const Color(0xFF616161),
              onChanged: (value) {
                setState(() {
                  _islamicModeEnabled = value;
                });
              },
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPrayerTimesCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A2640),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            "Today's Prayers",
            style: TextStyle(
              color: AppColors.gold,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 12),
          ...List<Widget>.generate(_prayerTimes.length, (index) {
            final Map<String, String> prayer = _prayerTimes[index];
            final bool isNext = index == _nextPrayerIndex;
            final bool isCompleted = index < _nextPrayerIndex;

            Color statusColor = const Color(0xFF9E9E9E);
            if (isCompleted) {
              statusColor = const Color(0xFF4CAF50);
            } else if (isNext) {
              statusColor = AppColors.accent;
            }

            return Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color: isNext ? const Color(0xFF243050) : Colors.transparent,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      prayer['name'] ?? '',
                      style: const TextStyle(
                        color: AppColors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  Text(
                    prayer['time'] ?? '',
                    style: const TextStyle(
                      color: AppColors.accent,
                      fontSize: 15,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(width: 10),
                  Container(
                    width: 10,
                    height: 10,
                    decoration: BoxDecoration(
                      color: statusColor,
                      shape: BoxShape.circle,
                    ),
                  ),
                ],
              ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildNextPrayerCard() {
    const Color prayerLedColor = AppColors.purple;
    final String name = _nextPrayerName.isNotEmpty ? _nextPrayerName : '—';
    final String eta = _nextPrayerEta.isNotEmpty ? _nextPrayerEta : '—';

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: const Color(0xFFFFF5E0).withValues(alpha: 0.55),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFFFFF5E0).withValues(alpha: 0.2),
            blurRadius: 16,
            spreadRadius: 0.5,
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            name,
            style: const TextStyle(
              color: AppColors.white,
              fontSize: 28,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            eta,
            style: const TextStyle(
              color: AppColors.accent,
              fontSize: 16,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Spotify will pause automatically 🎵',
            style: TextStyle(
              color: AppColors.softWhite,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              const Text(
                'LED Preview',
                style: TextStyle(
                  color: AppColors.softWhite,
                  fontSize: 12,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                width: 14,
                height: 14,
                decoration: const BoxDecoration(
                  color: prayerLedColor,
                  shape: BoxShape.circle,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildHadithCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Expanded(
                child: Text(
                  "📖 Today's Hadith",
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              IconButton(
                onPressed: () {},
                icon: const Icon(Icons.refresh_rounded),
                color: AppColors.softWhite,
                tooltip: 'Refresh',
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          const SizedBox(height: 4),
          Builder(builder: (context) {
            final hadithText = _hadith.isNotEmpty
                ? _hadith
                : 'The best of you are those with the best character.';
            return Directionality(
              textDirection: _detectDirection(hadithText),
              child: Text(
                hadithText,
                style: const TextStyle(
                  color: AppColors.softWhite,
                  fontSize: 13,
                  fontStyle: FontStyle.italic,
                  height: 1.5,
                ),
              ),
            );
          }),
          const SizedBox(height: 8),
          Text(
            _hadithSource.isNotEmpty ? '— $_hadithSource' : '— Sahih Bukhari',
            style: const TextStyle(
              color: AppColors.gold,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHijriCard() {
    final String subtitle = _isRamadan ? 'Ramadan Kareem 🌙' : '';

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
            _hijriDate.isNotEmpty ? '📅 $_hijriDate' : '📅 —',
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.gold,
              fontSize: 16,
              fontWeight: FontWeight.w700,
            ),
          ),
          if (subtitle.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              subtitle,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: AppColors.softWhite,
                fontSize: 13,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSunnahTipCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(18),
      ),
      child: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.nightlight_round, color: AppColors.gold, size: 24),
          SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  "Tonight's Sunnah Tip",
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                SizedBox(height: 8),
                Builder(builder: (context) {
                  const tip = 'Sleep on your right side as the Prophet ﷺ recommended';
                  return Directionality(
                    textDirection: _detectDirection(tip),
                    child: Text(
                      tip,
                      style: const TextStyle(
                        color: AppColors.softWhite,
                        fontSize: 13,
                        fontStyle: FontStyle.italic,
                        height: 1.4,
                      ),
                    ),
                  );
                }),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
