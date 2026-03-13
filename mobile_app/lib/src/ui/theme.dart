import 'package:flutter/material.dart';

class SmartBedPalette {
  SmartBedPalette._();

  static const Color background = Color(0xFF050816);
  static const Color surfaceDark = Color(0xFF0B1020);
  static const Color surfaceLight = Color(0xFF111827);
  static const Color accent = Color(0xFF4F46E5);
  static const Color secondaryAccent = Color(0xFF22D3EE);
  static const Color connected = Color(0xFF22C55E);
  static const Color warning = Color(0xFFF59E0B);
  static const Color danger = Color(0xFFEF4444);
  static const Color bodyText = Color(0xFF9CA3AF);
}

ThemeData buildSmartBedTheme() {
  const fontFallback = <String>[
    'Inter',
    '.SF Pro Text',
    '.SF Pro Display',
    'Roboto',
    'Helvetica Neue',
    'Arial',
  ];

  final base = ThemeData.dark(useMaterial3: true);
  final scheme = const ColorScheme.dark(
    primary: SmartBedPalette.accent,
    secondary: SmartBedPalette.secondaryAccent,
    surface: SmartBedPalette.surfaceDark,
    onPrimary: Colors.white,
    onSecondary: Colors.black,
    onSurface: Colors.white,
  );

  TextStyle? headline(TextStyle? style) => style?.copyWith(
    color: Colors.white,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.2,
    fontFamilyFallback: fontFallback,
  );

  TextStyle? body(TextStyle? style) => style?.copyWith(
    color: SmartBedPalette.bodyText,
    height: 1.42,
    fontFamilyFallback: fontFallback,
  );

  return base.copyWith(
    colorScheme: scheme,
    scaffoldBackgroundColor: SmartBedPalette.background,
    canvasColor: SmartBedPalette.background,
    cardTheme: CardThemeData(
      color: SmartBedPalette.surfaceDark,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: SmartBedPalette.surfaceLight,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      side: BorderSide(
        color: SmartBedPalette.secondaryAccent.withValues(alpha: 0.22),
      ),
      labelStyle: const TextStyle(
        color: Colors.white,
        fontWeight: FontWeight.w600,
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 74,
      backgroundColor: SmartBedPalette.surfaceDark.withValues(alpha: 0.92),
      indicatorColor: SmartBedPalette.secondaryAccent.withValues(alpha: 0.2),
      labelTextStyle: WidgetStateProperty.resolveWith<TextStyle?>(
        (states) => TextStyle(
          color: states.contains(WidgetState.selected)
              ? Colors.white
              : SmartBedPalette.bodyText.withValues(alpha: 0.82),
          fontWeight: states.contains(WidgetState.selected)
              ? FontWeight.w700
              : FontWeight.w500,
          fontFamilyFallback: fontFallback,
        ),
      ),
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: Colors.white,
      elevation: 0,
    ),
    textTheme: base.textTheme.copyWith(
      displayLarge: headline(base.textTheme.displayLarge),
      displayMedium: headline(base.textTheme.displayMedium),
      displaySmall: headline(base.textTheme.displaySmall),
      headlineLarge: headline(base.textTheme.headlineLarge)?.copyWith(
        fontWeight: FontWeight.w800,
        letterSpacing: -0.5,
      ),
      headlineMedium: headline(base.textTheme.headlineMedium)?.copyWith(
        fontWeight: FontWeight.w800,
        letterSpacing: -0.2,
      ),
      titleLarge: headline(base.textTheme.titleLarge),
      titleMedium: headline(base.textTheme.titleMedium),
      titleSmall: headline(base.textTheme.titleSmall),
      bodyLarge: body(base.textTheme.bodyLarge),
      bodyMedium: body(base.textTheme.bodyMedium),
      bodySmall: body(base.textTheme.bodySmall),
      labelLarge: base.textTheme.labelLarge?.copyWith(
        color: Colors.white,
        fontWeight: FontWeight.w600,
        fontFamilyFallback: fontFallback,
      ),
      labelMedium: base.textTheme.labelMedium?.copyWith(
        fontFamilyFallback: fontFallback,
      ),
      labelSmall: base.textTheme.labelSmall?.copyWith(
        fontFamilyFallback: fontFallback,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: SmartBedPalette.surfaceDark.withValues(alpha: 0.82),
      labelStyle: const TextStyle(color: SmartBedPalette.bodyText),
      hintStyle: TextStyle(color: SmartBedPalette.bodyText.withValues(alpha: 0.8)),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: BorderSide(
          color: SmartBedPalette.secondaryAccent.withValues(alpha: 0.2),
        ),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: BorderSide(
          color: SmartBedPalette.secondaryAccent.withValues(alpha: 0.2),
        ),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: BorderSide(
          color: SmartBedPalette.secondaryAccent.withValues(alpha: 0.55),
        ),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: SmartBedPalette.danger),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: SmartBedPalette.danger),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: SmartBedPalette.accent,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: SmartBedPalette.accent,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: Colors.white,
        side: BorderSide(
          color: SmartBedPalette.secondaryAccent.withValues(alpha: 0.4),
        ),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      ),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        backgroundColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return SmartBedPalette.accent.withValues(alpha: 0.2);
          }
          return SmartBedPalette.surfaceDark.withValues(alpha: 0.65);
        }),
        side: WidgetStatePropertyAll(
          BorderSide(
            color: SmartBedPalette.secondaryAccent.withValues(alpha: 0.3),
          ),
        ),
        foregroundColor: const WidgetStatePropertyAll(Colors.white),
      ),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: SmartBedPalette.secondaryAccent,
    ),
    sliderTheme: base.sliderTheme.copyWith(
      activeTrackColor: SmartBedPalette.secondaryAccent,
      thumbColor: SmartBedPalette.accent,
      inactiveTrackColor: SmartBedPalette.surfaceLight,
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return SmartBedPalette.secondaryAccent;
        }
        return SmartBedPalette.bodyText;
      }),
      trackColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return SmartBedPalette.secondaryAccent.withValues(alpha: 0.4);
        }
        return SmartBedPalette.surfaceLight;
      }),
    ),
    iconTheme: const IconThemeData(color: SmartBedPalette.secondaryAccent),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: SmartBedPalette.surfaceLight,
      contentTextStyle: const TextStyle(color: Colors.white),
    ),
  );
}
