import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';
import '../qr/qr_scanner_screen.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});

  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  int _currentPage = 0;
  late final PageController _controller;

  static const List<_OnboardingPageData> _pages = [
    _OnboardingPageData(
      icon: Icons.bed,
      iconColor: AppColors.accent,
      title: 'Welcome to Danah 🛏️',
      subtitle:
          'Your AI-powered smart bed companion. Sleep smarter, wake better — every night.',
    ),
    _OnboardingPageData(
      icon: Icons.mosque,
      iconColor: AppColors.gold,
      title: 'Built for Muslims 🕌',
      subtitle:
          'Prayer time reminders, Sunnah sleep tips, Ramadan mode, and Quran-based wind-down routines — all built in.',
    ),
    _OnboardingPageData(
      icon: Icons.auto_awesome,
      iconColor: AppColors.accent,
      title: 'Meet Dana ✨',
      subtitle:
          'Your personal AI sleep companion. She remembers your routines, guides your nights, and speaks your language.',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _controller = PageController();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _goToNextPage() {
    if (_currentPage < 2) {
      _controller.nextPage(
        duration: const Duration(milliseconds: 280),
        curve: Curves.easeInOut,
      );
    }
  }

  void _goToQrScanner() {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => const QRScannerScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 14, 20, 18),
          child: Column(
            children: [
              _buildTopBar(),
              Expanded(
                child: PageView.builder(
                  controller: _controller,
                  itemCount: _pages.length,
                  onPageChanged: (index) {
                    setState(() {
                      _currentPage = index;
                    });
                  },
                  itemBuilder: (context, index) {
                    final _OnboardingPageData page = _pages[index];
                    return _buildPage(page);
                  },
                ),
              ),
              _buildBottomNav(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTopBar() {
    return SizedBox(
      height: 34,
      child: Row(
        children: [
          const Spacer(),
          if (_currentPage < 2)
            TextButton(
              onPressed: _goToQrScanner,
              style: TextButton.styleFrom(
                foregroundColor: AppColors.softWhite.withValues(alpha: 0.8),
                textStyle: const TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              child: const Text('Skip'),
            )
          else
            const SizedBox(width: 54),
        ],
      ),
    );
  }

  Widget _buildPage(_OnboardingPageData data) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 8),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            data.icon,
            size: 100,
            color: data.iconColor,
          ),
          const SizedBox(height: 30),
          Text(
            data.title,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.white,
              fontSize: 26,
              fontWeight: FontWeight.w700,
              height: 1.2,
            ),
          ),
          const SizedBox(height: 16),
          Text(
            data.subtitle,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.softWhite,
              fontSize: 16,
              height: 1.55,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBottomNav() {
    final bool isLastPage = _currentPage == 2;
    return Column(
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: List<Widget>.generate(_pages.length, (index) {
            final bool isActive = index == _currentPage;
            return AnimatedContainer(
              duration: const Duration(milliseconds: 220),
              margin: const EdgeInsets.symmetric(horizontal: 6),
              width: isActive ? 12 : 8,
              height: isActive ? 12 : 8,
              decoration: BoxDecoration(
                color: isActive ? AppColors.accent : const Color(0xFF727C95),
                shape: BoxShape.circle,
              ),
            );
          }),
        ),
        const SizedBox(height: 20),
        if (!isLastPage)
          Row(
            children: [
              const Spacer(),
              FilledButton(
                onPressed: _goToNextPage,
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.accent,
                  foregroundColor: AppColors.background,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 13,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14),
                  ),
                ),
                child: const Text(
                  'Next →',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          )
        else
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: _goToQrScanner,
              style: FilledButton.styleFrom(
                backgroundColor: AppColors.accent,
                foregroundColor: AppColors.background,
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                ),
              ),
              child: const Text(
                'Get Started 🚀',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _OnboardingPageData {
  const _OnboardingPageData({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
  });

  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
}
