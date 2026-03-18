import 'package:flutter/material.dart';

import '../screens/chat/dana_chat_screen.dart';
import '../screens/home/home_screen.dart';
import '../screens/islamic/islamic_mode_screen.dart';
import '../screens/report/sleep_report_screen.dart';
import '../screens/settings/settings_screen.dart';

class MainNav extends StatefulWidget {
  const MainNav({super.key});

  @override
  State<MainNav> createState() => _MainNavState();
}

class _MainNavState extends State<MainNav> {
  int _currentIndex = 0;

  final List<Widget> _screens = const <Widget>[
    HomeScreen(),
    DanaChatScreen(),
    IslamicModeScreen(),
    SleepReportScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _screens[_currentIndex],
      bottomNavigationBar: BottomNavigationBar(
        backgroundColor: const Color(0xFF0D1B2E),
        selectedItemColor: const Color(0xFF00D4FF),
        unselectedItemColor: Colors.grey,
        currentIndex: _currentIndex,
        type: BottomNavigationBarType.fixed,
        onTap: (i) => setState(() => _currentIndex = i),
        items: const <BottomNavigationBarItem>[
          BottomNavigationBarItem(icon: Icon(Icons.home), label: 'Home'),
          BottomNavigationBarItem(icon: Icon(Icons.auto_awesome), label: 'Dana'),
          BottomNavigationBarItem(icon: Icon(Icons.mosque), label: 'Islamic'),
          BottomNavigationBarItem(icon: Icon(Icons.bar_chart), label: 'Report'),
          BottomNavigationBarItem(icon: Icon(Icons.settings), label: 'Settings'),
        ],
      ),
    );
  }
}
