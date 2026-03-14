import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

class SubscriptionScreen extends StatefulWidget {
  const SubscriptionScreen({super.key});

  @override
  State<SubscriptionScreen> createState() => _SubscriptionScreenState();
}

class _SubscriptionScreenState extends State<SubscriptionScreen> {
  String _selectedPlan = 'premium';

  String get _selectedPlanLabel {
    switch (_selectedPlan) {
      case 'free':
        return 'Free';
      case 'pro':
        return 'Pro';
      default:
        return 'Premium';
    }
  }

  String get _ctaLabel {
    switch (_selectedPlan) {
      case 'free':
        return 'Continue with Free';
      case 'pro':
        return 'Start Pro - KD 9.99/mo';
      default:
        return 'Start Premium - KD 4.99/mo';
    }
  }

  Color get _ctaColor {
    switch (_selectedPlan) {
      case 'free':
        return const Color(0xFF6B7280);
      case 'pro':
        return AppColors.gold;
      default:
        return AppColors.accent;
    }
  }

  Color get _ctaTextColor {
    switch (_selectedPlan) {
      case 'pro':
        return AppColors.background;
      default:
        return AppColors.white;
    }
  }

  void _onContinue() {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('$_selectedPlanLabel selected! Payment coming soon. \u{1F680}'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildTopBar(),
              const SizedBox(height: 16),
              _buildHeroSection(),
              const SizedBox(height: 16),
              _buildPlanCard(
                planKey: 'free',
                badgeText: 'FREE',
                badgeColor: const Color(0xFF7B849D),
                price: 'KD 0',
                priceColor: AppColors.white,
                features: const [
                  'Basic bed control',
                  'Limited Dana chat (5 messages/day)',
                  'Standard scenes',
                ],
                checkColor: const Color(0xFFB0B7CA),
              ),
              const SizedBox(height: 10),
              _buildPlanCard(
                planKey: 'premium',
                badgeText: 'PREMIUM',
                badgeColor: AppColors.accent,
                price: 'KD 4.99',
                priceColor: AppColors.accent,
                features: const [
                  'Full Dana AI with memory',
                  'Unlimited chat',
                  'All smart scenes',
                  'Islamic Mode full access',
                  'Partner Mode',
                  'Sleep insights & recovery score',
                ],
                checkColor: AppColors.accent,
                showPopularTag: true,
              ),
              const SizedBox(height: 10),
              _buildPlanCard(
                planKey: 'pro',
                badgeText: 'PRO',
                badgeColor: AppColors.gold,
                price: 'KD 9.99',
                priceColor: AppColors.gold,
                features: const [
                  'Everything in Premium',
                  '3D Bed Visualizer',
                  'Sound Engine & Sleep Stories',
                  'Dream Journal + AI',
                  'Priority support',
                  'Early access to new features',
                ],
                checkColor: AppColors.gold,
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: _onContinue,
                  style: FilledButton.styleFrom(
                    backgroundColor: _ctaColor,
                    foregroundColor: _ctaTextColor,
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(16),
                    ),
                  ),
                  child: Text(
                    _ctaLabel,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 10),
              const Center(
                child: Text(
                  'Cancel anytime. No hidden fees. Payments via PayPal.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Color(0xFF8A94AF),
                    fontSize: 12,
                  ),
                ),
              ),
              const SizedBox(height: 14),
              const Center(
                child: Text(
                  'Built for Kuwait \u{1F1F0}\u{1F1FC} - More regions coming soon',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Color(0xFF7E88A2),
                    fontSize: 11,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTopBar() {
    return Row(
      children: [
        IconButton(
          onPressed: () => Navigator.of(context).maybePop(),
          icon: const Icon(Icons.arrow_back_ios_new_rounded),
          color: AppColors.white,
          tooltip: 'Back',
        ),
        const Expanded(
          child: Text(
            'Choose Your Plan \u{1F451}',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: AppColors.white,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        const SizedBox(width: 48),
      ],
    );
  }

  Widget _buildHeroSection() {
    return const Column(
      children: [
        Center(
          child: Icon(
            Icons.auto_awesome,
            color: AppColors.accent,
            size: 60,
          ),
        ),
        SizedBox(height: 10),
        Text(
          'Unlock the Full Danah Experience',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: AppColors.white,
            fontSize: 22,
            fontWeight: FontWeight.w700,
          ),
        ),
        SizedBox(height: 8),
        Text(
          'Sleep smarter every night with AI-powered personalization',
          textAlign: TextAlign.center,
          style: TextStyle(
            color: Color(0xFF9CA6BF),
            fontSize: 14,
          ),
        ),
      ],
    );
  }

  Widget _buildPlanCard({
    required String planKey,
    required String badgeText,
    required Color badgeColor,
    required String price,
    required Color priceColor,
    required List<String> features,
    required Color checkColor,
    bool showPopularTag = false,
  }) {
    final bool isSelected = _selectedPlan == planKey;

    return InkWell(
      borderRadius: BorderRadius.circular(16),
      onTap: () {
        setState(() {
          _selectedPlan = planKey;
        });
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 12),
        decoration: BoxDecoration(
          color: const Color(0xFF1A2740),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isSelected
                ? AppColors.accent
                : AppColors.softWhite.withValues(alpha: 0.18),
            width: isSelected ? 1.4 : 1,
          ),
          boxShadow: isSelected
              ? [
                  BoxShadow(
                    color: AppColors.accent.withValues(alpha: 0.3),
                    blurRadius: 18,
                    spreadRadius: 0.8,
                    offset: const Offset(0, 0),
                  ),
                ]
              : [],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: badgeColor.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: badgeColor.withValues(alpha: 0.45),
                      width: 1,
                    ),
                  ),
                  child: Text(
                    badgeText,
                    style: TextStyle(
                      color: badgeColor,
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                const Spacer(),
                if (showPopularTag)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.accent,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Text(
                      'MOST POPULAR',
                      style: TextStyle(
                        color: AppColors.background,
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 10),
            Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  price,
                  style: TextStyle(
                    color: priceColor,
                    fontSize: 28,
                    fontWeight: FontWeight.w700,
                    height: 1,
                  ),
                ),
                const SizedBox(width: 6),
                const Padding(
                  padding: EdgeInsets.only(bottom: 4),
                  child: Text(
                    '/month',
                    style: TextStyle(
                      color: Color(0xFF8C97B2),
                      fontSize: 14,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            ...features.map((feature) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.check,
                      color: checkColor,
                      size: 18,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        feature,
                        style: const TextStyle(
                          color: AppColors.softWhite,
                          fontSize: 13,
                          height: 1.35,
                        ),
                      ),
                    ),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}
