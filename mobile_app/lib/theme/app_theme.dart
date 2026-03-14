import 'package:flutter/material.dart';

class AppColors {
  static const Color background = Color(0xFF0A1628);
  static const Color accent = Color(0xFF00D4FF);
  static const Color purple = Color(0xFF7B68EE);
  static const Color orange = Color(0xFFFF6B35);
  static const Color white = Color(0xFFFFFFFF);
  static const Color softWhite = Color(0xFFE8E8E8);
  static const Color cardBg = Color(0xFF1A2640);
  static const Color gold = Color(0xFFFFD700);
}

class AppTheme {
  static final ThemeData darkTheme = ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    fontFamily: 'Poppins',
    scaffoldBackgroundColor: AppColors.background,
    colorScheme: const ColorScheme.dark(
      primary: AppColors.accent,
      secondary: AppColors.purple,
      surface: AppColors.cardBg,
      onPrimary: AppColors.background,
      onSecondary: AppColors.white,
      onSurface: AppColors.white,
    ),
    textTheme: const TextTheme(
      headlineMedium: TextStyle(
        color: AppColors.white,
        fontWeight: FontWeight.w700,
      ),
      titleMedium: TextStyle(
        color: AppColors.white,
        fontWeight: FontWeight.w600,
      ),
      bodyMedium: TextStyle(
        color: AppColors.softWhite,
      ),
    ),
    cardTheme: const CardThemeData(
      color: AppColors.cardBg,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.all(Radius.circular(18)),
      ),
    ),
  );
}
