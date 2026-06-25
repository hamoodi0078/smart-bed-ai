import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:table_calendar/table_calendar.dart';

import '../../services/api_service.dart';
import '../../theme/app_theme.dart';
import '../../widgets/network_banner.dart';
import '../../widgets/shimmer_loader.dart';

// Returns TextDirection.rtl when text contains Arabic characters.
TextDirection _detectDirection(String text) {
  return RegExp(r'[؀-ۿ]').hasMatch(text)
      ? TextDirection.rtl
      : TextDirection.ltr;
}

// ─── Data model ───────────────────────────────────────────────────────────────

class _IslamicData {
  const _IslamicData({
    required this.prayerTimes,
    required this.nextPrayerIndex,
    required this.nextPrayerName,
    required this.nextPrayerEta,
    required this.isRamadan,
    required this.hijriDate,
    required this.hadith,
    required this.hadithSource,
  });

  final List<Map<String, String>> prayerTimes;
  final int nextPrayerIndex;
  final String nextPrayerName;
  final String nextPrayerEta;
  final bool isRamadan;
  final String hijriDate;
  final String hadith;
  final String hadithSource;

  static const _IslamicData empty = _IslamicData(
    prayerTimes: [
      {'name': 'Fajr', 'time': '--:--'},
      {'name': 'Dhuhr', 'time': '--:--'},
      {'name': 'Asr', 'time': '--:--'},
      {'name': 'Maghrib', 'time': '--:--'},
      {'name': 'Isha', 'time': '--:--'},
    ],
    nextPrayerIndex: 0,
    nextPrayerName: '',
    nextPrayerEta: '',
    isRamadan: false,
    hijriDate: '',
    hadith: '',
    hadithSource: '',
  );
}

// ─── Provider ────────────────────────────────────────────────────────────────

final islamicDataProvider =
    FutureProvider.autoDispose<_IslamicData>((ref) async {
  final data = await ApiService.getIslamicOverview();
  if (data['error'] == true) {
    throw Exception(data['message'] ?? 'Failed to load Islamic data');
  }

  const order = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha'];
  final times = data['prayer_times'];
  final List<Map<String, String>> prayerTimes;

  if (times is Map) {
    prayerTimes = [
      for (final name in order)
        {
          'name': name,
          'time': times[name.toLowerCase()] as String? ??
              times[name] as String? ??
              '--:--',
        }
    ];
  } else {
    prayerTimes = _IslamicData.empty.prayerTimes;
  }

  final nextPrayer = data['next_prayer'] as String? ?? '';
  final nextIdx = order.indexWhere(
    (n) => n.toLowerCase() == nextPrayer.toLowerCase(),
  );

  return _IslamicData(
    prayerTimes: prayerTimes,
    nextPrayerIndex: nextIdx < 0 ? 0 : nextIdx,
    nextPrayerName: nextPrayer,
    nextPrayerEta: data['next_prayer_eta'] as String? ?? '',
    isRamadan: data['is_ramadan'] as bool? ?? false,
    hijriDate: data['hijri_date'] as String? ?? '',
    hadith: data['hadith'] as String? ?? '',
    hadithSource: data['hadith_source'] as String? ?? '',
  );
});

// ─── Screen ───────────────────────────────────────────────────────────────────

class IslamicScreen extends ConsumerStatefulWidget {
  const IslamicScreen({super.key});

  @override
  ConsumerState<IslamicScreen> createState() => _IslamicScreenState();
}

class _IslamicScreenState extends ConsumerState<IslamicScreen> {
  bool _islamicModeEnabled = true;
  DateTime _focusedDay = DateTime.now();
  DateTime? _selectedDay;

  Future<void> _onRefresh() async {
    ref.invalidate(islamicDataProvider);
  }

  @override
  Widget build(BuildContext context) {
    final islamicAsync = ref.watch(islamicDataProvider);
    final data = islamicAsync.valueOrNull ?? _IslamicData.empty;

    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: SafeArea(
        child: Column(
          children: [
            const NetworkBanner(),
            if (islamicAsync.isLoading && islamicAsync.valueOrNull == null)
              Expanded(
                child: SingleChildScrollView(
                  child: ShimmerLoader.islamicSkeleton(),
                ),
              )
            else ...[
              if (islamicAsync.isLoading)
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
                      _buildTopBar(),
                      if (islamicAsync.hasError) ...[
                        const SizedBox(height: 12),
                        _buildErrorBanner(islamicAsync.error.toString()
                            .replaceAll('Exception: ', '')),
                      ],
                      const SizedBox(height: 14),
                      _buildPrayerTimesCard(data),
                      const SizedBox(height: 14),
                      _buildNextPrayerCard(data),
                      const SizedBox(height: 14),
                      _buildHadithCard(data),
                      const SizedBox(height: 14),
                      _buildHijriCard(data),
                      const SizedBox(height: 14),
                      _buildPrayerCalendarCard(),
                      const SizedBox(height: 14),
                      _buildSunnahTipCard(),
                    ],
                  ),
                ),
              ),
            ),
            ], // end else
          ],
        ),
      ),
    );
  }

  Widget _buildErrorBanner(String message) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: AppColors.orange.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.orange.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          const Icon(Icons.wifi_off_rounded,
              color: AppColors.orange, size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Showing cached data — $message',
              style: const TextStyle(color: AppColors.orange, fontSize: 12),
            ),
          ),
          IconButton(
            onPressed: _onRefresh,
            icon: const Icon(Icons.refresh_rounded,
                color: AppColors.orange, size: 18),
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
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go('/dashboard');
            }
          },
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
            child: Semantics(
              label: 'Islamic mode',
              toggled: _islamicModeEnabled,
              child: Switch(
                value: _islamicModeEnabled,
                activeThumbColor: AppColors.accent,
                activeTrackColor: AppColors.accent.withValues(alpha: 0.4),
                inactiveThumbColor: const Color(0xFFB0B0B0),
                inactiveTrackColor: const Color(0xFF616161),
                onChanged: (value) =>
                    setState(() => _islamicModeEnabled = value),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPrayerTimesCard(_IslamicData data) {
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
          ...List<Widget>.generate(data.prayerTimes.length, (index) {
            final prayer = data.prayerTimes[index];
            final isNext = index == data.nextPrayerIndex;
            final isCompleted = index < data.nextPrayerIndex;

            Color statusColor = const Color(0xFF9E9E9E);
            if (isCompleted) statusColor = const Color(0xFF4CAF50);
            if (isNext) statusColor = AppColors.accent;

            return Semantics(
              label: '${prayer['name']} prayer at ${prayer['time']}'
                  '${isNext ? ', next prayer' : isCompleted ? ', completed' : ''}',
              child: Container(
              margin: const EdgeInsets.only(bottom: 8),
              padding: const EdgeInsets.symmetric(
                  horizontal: 12, vertical: 10),
              decoration: BoxDecoration(
                color:
                    isNext ? const Color(0xFF243050) : Colors.transparent,
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
            ),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildNextPrayerCard(_IslamicData data) {
    const Color prayerLedColor = AppColors.purple;
    final String name =
        data.nextPrayerName.isNotEmpty ? data.nextPrayerName : '—';
    final String eta =
        data.nextPrayerEta.isNotEmpty ? data.nextPrayerEta : '—';

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
            style: TextStyle(color: AppColors.softWhite, fontSize: 12),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              const Text(
                'LED Preview',
                style: TextStyle(
                    color: AppColors.softWhite, fontSize: 12),
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

  Widget _buildHadithCard(_IslamicData data) {
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
                onPressed: _onRefresh,
                icon: const Icon(Icons.refresh_rounded),
                color: AppColors.softWhite,
                tooltip: 'Refresh',
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          const SizedBox(height: 4),
          Builder(builder: (context) {
            final hadithText = data.hadith.isNotEmpty
                ? data.hadith
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
            data.hadithSource.isNotEmpty
                ? '— ${data.hadithSource}'
                : '— Sahih Bukhari',
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

  Widget _buildHijriCard(_IslamicData data) {
    final String subtitle = data.isRamadan ? 'Ramadan Kareem 🌙' : '';

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
            data.hijriDate.isNotEmpty ? '📅 ${data.hijriDate}' : '📅 —',
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
                  color: AppColors.softWhite, fontSize: 13),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildPrayerCalendarCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 4),
      decoration: BoxDecoration(
        color: AppColors.cardBg,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 4, 16, 8),
            child: Text(
              '📅 Prayer Calendar',
              style: TextStyle(
                color: AppColors.gold,
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          TableCalendar<void>(
            firstDay: DateTime.utc(2020, 1, 1),
            lastDay: DateTime.utc(2030, 12, 31),
            focusedDay: _focusedDay,
            selectedDayPredicate: (day) => isSameDay(_selectedDay, day),
            onDaySelected: (selected, focused) {
              setState(() {
                _selectedDay = selected;
                _focusedDay = focused;
              });
            },
            onPageChanged: (focused) =>
                setState(() => _focusedDay = focused),
            calendarFormat: CalendarFormat.month,
            availableCalendarFormats: const {
              CalendarFormat.month: 'Month'
            },
            headerStyle: const HeaderStyle(
              titleCentered: true,
              titleTextStyle: TextStyle(
                color: AppColors.white,
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
              leftChevronIcon:
                  Icon(Icons.chevron_left, color: AppColors.accent),
              rightChevronIcon:
                  Icon(Icons.chevron_right, color: AppColors.accent),
              formatButtonVisible: false,
              headerPadding:
                  EdgeInsets.symmetric(vertical: 6),
            ),
            daysOfWeekStyle: const DaysOfWeekStyle(
              weekdayStyle: TextStyle(
                  color: AppColors.softWhite, fontSize: 12),
              weekendStyle:
                  TextStyle(color: AppColors.gold, fontSize: 12),
            ),
            calendarStyle: CalendarStyle(
              outsideDaysVisible: false,
              defaultTextStyle:
                  const TextStyle(color: AppColors.white),
              weekendTextStyle:
                  const TextStyle(color: AppColors.gold),
              todayDecoration: BoxDecoration(
                color: AppColors.accent.withValues(alpha: 0.35),
                shape: BoxShape.circle,
              ),
              todayTextStyle: const TextStyle(
                color: AppColors.accent,
                fontWeight: FontWeight.w700,
              ),
              selectedDecoration: const BoxDecoration(
                color: AppColors.purple,
                shape: BoxShape.circle,
              ),
              selectedTextStyle: const TextStyle(
                color: AppColors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
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
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.nightlight_round, color: AppColors.gold, size: 24),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  "Tonight's Sunnah Tip",
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Builder(builder: (context) {
                  const tip =
                      'Sleep on your right side as the Prophet ﷺ recommended';
                  return Directionality(
                    textDirection: _detectDirection(tip),
                    child: Text(
                      tip,
                      style: TextStyle(
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
