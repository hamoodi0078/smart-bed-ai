import 'package:flutter/material.dart';

import '../../theme/app_theme.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  bool _notificationsEnabled = true;
  bool _islamicModeEnabled = true;
  bool _partnerModeEnabled = false;
  String _selectedLanguage = 'English';
  String _selectedDana = 'Calm Dana';

  void _showComingSoon() {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Coming soon')),
    );
  }

  void _showDanaPicker() {
    const List<String> options = [
      'Calm Dana',
      'Motivational Dana',
      'Islamic Dana',
    ];

    showModalBottomSheet<void>(
      context: context,
      backgroundColor: const Color(0xFF111D34),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: options.map((option) {
              return ListTile(
                title: Text(
                  option,
                  style: const TextStyle(color: AppColors.white),
                ),
                onTap: () {
                  setState(() {
                    _selectedDana = option;
                  });
                  Navigator.of(context).pop();
                },
              );
            }).toList(),
          ),
        );
      },
    );
  }

  void _showLanguagePicker() {
    const List<String> options = ['English', 'Arabic', 'Urdu'];

    showModalBottomSheet<void>(
      context: context,
      backgroundColor: const Color(0xFF111D34),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      builder: (context) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: options.map((option) {
              return ListTile(
                title: Text(
                  option,
                  style: const TextStyle(color: AppColors.white),
                ),
                onTap: () {
                  setState(() {
                    _selectedLanguage = option;
                  });
                  Navigator.of(context).pop();
                },
              );
            }).toList(),
          ),
        );
      },
    );
  }

  Future<void> _confirmSignOut() async {
    final bool? shouldSignOut = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1A2740),
          title: const Text('Sign Out'),
          content: const Text('Are you sure you want to sign out?'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              style: FilledButton.styleFrom(
                backgroundColor: Colors.red,
                foregroundColor: AppColors.white,
              ),
              child: const Text('Confirm'),
            ),
          ],
        );
      },
    );

    if (shouldSignOut == true && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Signed out')),
      );
    }
  }

  Future<void> _confirmResetSettings() async {
    final bool? shouldReset = await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1A2740),
          title: const Text('Reset All Settings'),
          content: const Text(
            'This will reset all preferences to default values. Continue?',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              style: FilledButton.styleFrom(
                backgroundColor: Colors.red,
                foregroundColor: AppColors.white,
              ),
              child: const Text('Confirm'),
            ),
          ],
        );
      },
    );

    if (shouldReset == true && mounted) {
      setState(() {
        _notificationsEnabled = true;
        _islamicModeEnabled = true;
        _partnerModeEnabled = false;
        _selectedLanguage = 'English';
        _selectedDana = 'Calm Dana';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Settings reset to defaults')),
      );
    }
  }

  Widget _buildSection(String title, List<Widget> children) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            color: AppColors.white,
            fontSize: 16,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 8),
        Container(
          width: double.infinity,
          decoration: BoxDecoration(
            color: const Color(0xFF1A2740),
            borderRadius: BorderRadius.circular(14),
          ),
          child: Column(children: children),
        ),
      ],
    );
  }

  Widget _buildProfileCard() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF1A2740),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: const BoxDecoration(
              color: AppColors.accent,
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.person,
              color: AppColors.white,
              size: 40,
            ),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Hamoud',
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                SizedBox(height: 2),
                Text(
                  'Premium Member 👑',
                  style: TextStyle(
                    color: AppColors.gold,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          OutlinedButton(
            onPressed: _showComingSoon,
            style: OutlinedButton.styleFrom(
              foregroundColor: AppColors.softWhite,
              side: BorderSide(
                color: AppColors.softWhite.withValues(alpha: 0.3),
              ),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(10),
              ),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            ),
            child: const Text(
              'Edit Profile',
              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
            ),
          ),
        ],
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
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 2),
                child: Text(
                  'Settings ⚙️',
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(height: 14),
              _buildProfileCard(),
              const SizedBox(height: 16),
              _buildSection(
                'Preferences',
                [
                  SwitchListTile(
                    title: const Text(
                      'Push Notifications',
                      style: TextStyle(color: AppColors.white),
                    ),
                    value: _notificationsEnabled,
                    activeThumbColor: AppColors.accent,
                    activeTrackColor: AppColors.accent.withValues(alpha: 0.4),
                    onChanged: (value) {
                      setState(() {
                        _notificationsEnabled = value;
                      });
                    },
                  ),
                  SwitchListTile(
                    title: const Text(
                      'Islamic Mode',
                      style: TextStyle(color: AppColors.white),
                    ),
                    value: _islamicModeEnabled,
                    activeThumbColor: AppColors.accent,
                    activeTrackColor: AppColors.accent.withValues(alpha: 0.4),
                    onChanged: (value) {
                      setState(() {
                        _islamicModeEnabled = value;
                      });
                    },
                  ),
                  SwitchListTile(
                    title: const Text(
                      'Partner Mode',
                      style: TextStyle(color: AppColors.white),
                    ),
                    value: _partnerModeEnabled,
                    activeThumbColor: AppColors.accent,
                    activeTrackColor: AppColors.accent.withValues(alpha: 0.4),
                    onChanged: (value) {
                      setState(() {
                        _partnerModeEnabled = value;
                      });
                    },
                  ),
                ],
              ),
              const SizedBox(height: 14),
              _buildSection(
                'Dana Personality',
                [
                  ListTile(
                    title: const Text(
                      'Active Dana',
                      style: TextStyle(color: AppColors.white),
                    ),
                    subtitle: Text(
                      _selectedDana,
                      style: const TextStyle(
                        color: AppColors.accent,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    trailing: const Icon(
                      Icons.chevron_right,
                      color: AppColors.softWhite,
                    ),
                    onTap: _showDanaPicker,
                  ),
                ],
              ),
              const SizedBox(height: 14),
              _buildSection(
                'Language',
                [
                  ListTile(
                    title: const Text(
                      'App Language',
                      style: TextStyle(color: AppColors.white),
                    ),
                    subtitle: Text(
                      _selectedLanguage,
                      style: const TextStyle(
                        color: AppColors.accent,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    trailing: const Icon(
                      Icons.chevron_right,
                      color: AppColors.softWhite,
                    ),
                    onTap: _showLanguagePicker,
                  ),
                ],
              ),
              const SizedBox(height: 14),
              _buildSection(
                'Account',
                [
                  ListTile(
                    title: const Text(
                      'Subscription Plan',
                      style: TextStyle(color: AppColors.white),
                    ),
                    subtitle: const Text(
                      'Premium',
                      style: TextStyle(
                        color: AppColors.gold,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    trailing: const Icon(
                      Icons.chevron_right,
                      color: AppColors.softWhite,
                    ),
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) => const SubscriptionScreen(),
                        ),
                      );
                    },
                  ),
                  const Divider(height: 1, color: Color(0xFF2A3A57)),
                  ListTile(
                    title: const Text(
                      'Privacy Policy',
                      style: TextStyle(color: AppColors.white),
                    ),
                    trailing: const Icon(
                      Icons.chevron_right,
                      color: AppColors.softWhite,
                    ),
                    onTap: _showComingSoon,
                  ),
                  const Divider(height: 1, color: Color(0xFF2A3A57)),
                  ListTile(
                    title: const Text(
                      'Help & Support',
                      style: TextStyle(color: AppColors.white),
                    ),
                    trailing: const Icon(
                      Icons.chevron_right,
                      color: AppColors.softWhite,
                    ),
                    onTap: _showComingSoon,
                  ),
                ],
              ),
              const SizedBox(height: 14),
              _buildSection(
                'Danger Zone',
                [
                  ListTile(
                    leading: const Icon(Icons.logout, color: Colors.red),
                    title: const Text(
                      'Sign Out',
                      style: TextStyle(
                        color: Colors.red,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    onTap: _confirmSignOut,
                  ),
                  const Divider(height: 1, color: Color(0xFF2A3A57)),
                  ListTile(
                    leading: const Icon(Icons.warning_amber_rounded, color: Colors.red),
                    title: const Text(
                      'Reset All Settings',
                      style: TextStyle(
                        color: Colors.red,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    onTap: _confirmResetSettings,
                  ),
                ],
              ),
              const SizedBox(height: 18),
              const Center(
                child: Text(
                  'Danah Smart Bed v1.0 — Built with ❤️ in Kuwait',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Color(0xFF7F8BA7),
                    fontSize: 12,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class SubscriptionScreen extends StatelessWidget {
  const SubscriptionScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0A1628),
        foregroundColor: AppColors.white,
        title: const Text('Subscription'),
      ),
      body: const Center(
        child: Text(
          'Subscription details coming next.',
          style: TextStyle(color: AppColors.softWhite),
        ),
      ),
    );
  }
}
