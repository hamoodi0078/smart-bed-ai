import 'package:flutter/material.dart';
import 'home/home_screen.dart';
import 'islamic/islamic_screen.dart';
import 'report/report_screen.dart';
import 'settings/settings_screen.dart';
import 'dana/dana_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _currentIndex = 0;

  // These are your 5 screens in order
  final List<Widget> _screens = const [
    HomeScreen(),
    DanaScreen(),
    IslamicScreen(),
    ReportScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),

      // Show the current screen
      body: _screens[_currentIndex],

      // ✅ Nav bar lives HERE — not inside any screen
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF0F2040),
          border: Border(
            top: BorderSide(
              color: const Color(0xFF00D4FF).withOpacity(0.2),
              width: 1,
            ),
          ),
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (index) => setState(() => _currentIndex = index),
          backgroundColor: Colors.transparent,
          elevation: 0,
          type: BottomNavigationBarType.fixed,
          selectedItemColor: const Color(0xFF00D4FF),
          unselectedItemColor: const Color(0xFF94A3B8),
          selectedLabelStyle: const TextStyle(
            fontSize: 11,
            fontWeight: FontWeight.w600,
          ),
          unselectedLabelStyle: const TextStyle(
            fontSize: 11,
          ),
          items: const [
            BottomNavigationBarItem(
              icon: Icon(Icons.home_rounded),
              label: 'Home',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.auto_awesome_rounded),
              label: 'Dana',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.mosque_rounded),
              label: 'Islamic',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.bar_chart_rounded),
              label: 'Report',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.settings_rounded),
              label: 'Settings',
            ),
          ],
        ),
      ),
    );
  }
}
