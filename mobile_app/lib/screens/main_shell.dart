import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'home/home_screen.dart';
import 'islamic/islamic_screen.dart';
import 'report/sleep_report_screen.dart';
import 'settings/settings_screen.dart';
import 'dana/dana_screen.dart';
import 'dana/dana_chat_screen.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key});

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> with TickerProviderStateMixin {
  int _currentIndex = 0;
  late AnimationController _pulseCtrl;
  late Animation<double> _pulseScale;

  final List<Widget> _screens = const [
    HomeScreen(),
    DanaScreen(),
    IslamicScreen(),
    SleepReportScreen(),
    SettingsScreen(),
  ];

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    )..repeat(reverse: true);
    _pulseScale = Tween<double>(begin: 1.0, end: 1.12).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );
    _requestPermissions();
  }

  Future<void> _requestPermissions() async {
    await [
      Permission.microphone,
      Permission.notification,
    ].request();
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A1628),
      body: IndexedStack(index: _currentIndex, children: _screens),
      floatingActionButton: ScaleTransition(
        scale: _pulseScale,
        child: AnimatedBuilder(
          animation: _pulseCtrl,
          builder: (_, child) => FloatingActionButton(
            backgroundColor: const Color(0xFF7B68EE),
            elevation: 0,
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute<void>(builder: (_) => const DanaChatScreen()),
            ),
            child: Stack(
              alignment: Alignment.center,
              children: [
                // Outer glow that pulses with _pulseCtrl
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF7B68EE)
                            .withValues(alpha: 0.3 + _pulseCtrl.value * 0.35),
                        blurRadius: 20,
                        spreadRadius: 4,
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.auto_awesome_rounded, color: Colors.white, size: 26),
              ],
            ),
          ),
        ),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.endFloat,
      bottomNavigationBar: Container(
        decoration: BoxDecoration(
          color: const Color(0xFF0F2040),
          border: Border(
            top: BorderSide(
              color: const Color(0xFF00D4FF).withValues(alpha: 0.2),
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
          selectedLabelStyle: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
          unselectedLabelStyle: const TextStyle(fontSize: 11),
          items: const [
            BottomNavigationBarItem(icon: Icon(Icons.home_rounded), label: 'Home'),
            BottomNavigationBarItem(icon: Icon(Icons.auto_awesome_rounded), label: 'Dana'),
            BottomNavigationBarItem(icon: Icon(Icons.mosque_rounded), label: 'Islamic'),
            BottomNavigationBarItem(icon: Icon(Icons.bar_chart_rounded), label: 'Report'),
            BottomNavigationBarItem(icon: Icon(Icons.settings_rounded), label: 'Settings'),
          ],
        ),
      ),
    );
  }
}
