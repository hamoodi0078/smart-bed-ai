import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../theme/app_theme.dart';

/// Wraps [child] with a subscription gate.
///
/// If the user already has a paid plan the [child] is shown directly.
/// Otherwise the gate UI is displayed with an upgrade prompt.
class PremiumGateWrapper extends StatefulWidget {
  const PremiumGateWrapper({
    super.key,
    required this.featureName,
    required this.child,
    this.description,
    this.onUpgrade,
  });

  final String featureName;
  final Widget child;
  final String? description;
  final VoidCallback? onUpgrade;

  @override
  State<PremiumGateWrapper> createState() => _PremiumGateWrapperState();
}

class _PremiumGateWrapperState extends State<PremiumGateWrapper> {
  bool _checking = true;
  bool _isPremium = false;

  @override
  void initState() {
    super.initState();
    _checkSubscription();
  }

  Future<void> _checkSubscription() async {
    try {
      final data = await ApiService.getSubscriptionStatus();
      final tier = (data['tier'] ?? data['plan'] ?? '').toString().toLowerCase();
      final isPaid = tier == 'standard' || tier == 'pro' || tier == 'premium';
      if (mounted) {
        setState(() {
          _isPremium = isPaid;
          _checking = false;
        });
      }
    } catch (_) {
      // On error default to showing the gate (safe fallback)
      if (mounted) setState(() => _checking = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_checking) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: CircularProgressIndicator(color: AppColors.accent),
        ),
      );
    }
    if (_isPremium) return widget.child;
    return PremiumGate(
      featureName: widget.featureName,
      description: widget.description,
      onUpgrade: widget.onUpgrade,
    );
  }
}

class PremiumGate extends StatelessWidget {
  const PremiumGate({
    super.key,
    required this.featureName,
    this.description,
    this.onUpgrade,
  });

  final String featureName;
  final String? description;
  final VoidCallback? onUpgrade;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(20),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            AppColors.gold.withValues(alpha: 0.2),
            AppColors.orange.withValues(alpha: 0.1),
          ],
        ),
        border: Border.all(
          color: AppColors.gold.withValues(alpha: 0.5),
          width: 2,
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: AppColors.gold.withValues(alpha: 0.2),
              border: Border.all(
                color: AppColors.gold,
                width: 2,
              ),
            ),
            child: const Icon(
              Icons.star_rounded,
              color: AppColors.gold,
              size: 48,
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'Premium Feature',
            style: TextStyle(
              color: AppColors.gold,
              fontSize: 14,
              fontWeight: FontWeight.w700,
              letterSpacing: 1,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            featureName,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: AppColors.white,
              fontSize: 20,
              fontWeight: FontWeight.w700,
            ),
          ),
          if (description != null) ...[
            const SizedBox(height: 8),
            Text(
              description!,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: AppColors.softWhite.withValues(alpha: 0.8),
                fontSize: 14,
                height: 1.4,
              ),
            ),
          ],
          const SizedBox(height: 20),
          FilledButton.icon(
            onPressed: onUpgrade ?? () => _showUpgradeSheet(context),
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.gold,
              foregroundColor: AppColors.background,
              padding: const EdgeInsets.symmetric(
                horizontal: 32,
                vertical: 14,
              ),
            ),
            icon: const Icon(Icons.workspace_premium_rounded),
            label: const Text(
              'Upgrade to Premium',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }

  static void _showUpgradeSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => const _PremiumUpgradeSheet(),
    );
  }
}

class _PremiumUpgradeSheet extends StatelessWidget {
  const _PremiumUpgradeSheet();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: MediaQuery.of(context).size.height * 0.85,
      decoration: const BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        children: [
          Container(
            margin: const EdgeInsets.symmetric(vertical: 12),
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: AppColors.softWhite.withValues(alpha: 0.3),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: const BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: LinearGradient(
                        colors: [
                          AppColors.gold,
                          AppColors.orange,
                        ],
                      ),
                    ),
                    child: const Icon(
                      Icons.workspace_premium_rounded,
                      color: Colors.white,
                      size: 64,
                    ),
                  ),
                  const SizedBox(height: 20),
                  const Text(
                    'Upgrade to Premium',
                    style: TextStyle(
                      color: AppColors.white,
                      fontSize: 28,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Unlock all features and personalize your sleep experience',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: AppColors.softWhite.withValues(alpha: 0.8),
                      fontSize: 16,
                      height: 1.4,
                    ),
                  ),
                  const SizedBox(height: 32),
                  _buildFeatureList(),
                  const SizedBox(height: 32),
                  _buildPricingCards(),
                  const SizedBox(height: 24),
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: () {
                        Navigator.pop(context);
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Premium upgrade coming soon!'),
                            backgroundColor: AppColors.gold,
                          ),
                        );
                      },
                      style: FilledButton.styleFrom(
                        backgroundColor: AppColors.gold,
                        foregroundColor: AppColors.background,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                      child: const Text(
                        'Start Free Trial',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    '7 days free, then \$4.99/month',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: AppColors.softWhite.withValues(alpha: 0.6),
                      fontSize: 12,
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

  Widget _buildFeatureList() {
    return const Column(
      children: [
        _FeatureItem(
          icon: Icons.palette_rounded,
          title: 'Unlimited Scenes',
          description: 'Access 50+ premium sleep scenes',
        ),
        _FeatureItem(
          icon: Icons.stars_rounded,
          title: 'Advanced Analytics',
          description: 'Detailed sleep insights and trends',
        ),
        _FeatureItem(
          icon: Icons.psychology_rounded,
          title: 'AI Sleep Coach',
          description: 'Personalized sleep recommendations',
        ),
        _FeatureItem(
          icon: Icons.family_restroom_rounded,
          title: 'Family Sharing',
          description: 'Share with up to 5 family members',
        ),
        _FeatureItem(
          icon: Icons.cloud_sync_rounded,
          title: 'Cloud Backup',
          description: 'Never lose your sleep data',
        ),
      ],
    );
  }

  Widget _buildPricingCards() {
    return Row(
      children: [
        Expanded(
          child: _PricingCard(
            title: 'Monthly',
            price: '\$4.99',
            period: 'per month',
            isPopular: false,
            onTap: () {},
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _PricingCard(
            title: 'Yearly',
            price: '\$39.99',
            period: 'per year',
            savings: 'Save 33%',
            isPopular: true,
            onTap: () {},
          ),
        ),
      ],
    );
  }
}

class _FeatureItem extends StatelessWidget {
  const _FeatureItem({
    required this.icon,
    required this.title,
    required this.description,
  });

  final IconData icon;
  final String title;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.gold.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(icon, color: AppColors.gold, size: 24),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: AppColors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  description,
                  style: TextStyle(
                    color: AppColors.softWhite.withValues(alpha: 0.7),
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
          const Icon(
            Icons.check_circle_rounded,
            color: AppColors.gold,
            size: 20,
          ),
        ],
      ),
    );
  }
}

class _PricingCard extends StatelessWidget {
  const _PricingCard({
    required this.title,
    required this.price,
    required this.period,
    required this.isPopular,
    required this.onTap,
    this.savings,
  });

  final String title;
  final String price;
  final String period;
  final String? savings;
  final bool isPopular;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          color: isPopular
              ? AppColors.gold.withValues(alpha: 0.1)
              : AppColors.cardBg,
          border: Border.all(
            color: isPopular ? AppColors.gold : AppColors.softWhite.withValues(alpha: 0.2),
            width: isPopular ? 2 : 1,
          ),
        ),
        child: Column(
          children: [
            if (isPopular)
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 4,
                ),
                decoration: BoxDecoration(
                  color: AppColors.gold,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text(
                  'BEST VALUE',
                  style: TextStyle(
                    color: AppColors.background,
                    fontSize: 10,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            if (!isPopular) const SizedBox(height: 20),
            const SizedBox(height: 8),
            Text(
              title,
              style: TextStyle(
                color: isPopular ? AppColors.gold : AppColors.white,
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              price,
              style: TextStyle(
                color: isPopular ? AppColors.gold : AppColors.white,
                fontSize: 28,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              period,
              style: TextStyle(
                color: AppColors.softWhite.withValues(alpha: 0.6),
                fontSize: 12,
              ),
            ),
            if (savings != null) ...[
              const SizedBox(height: 8),
              Text(
                savings!,
                style: const TextStyle(
                  color: AppColors.gold,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
