import 'package:flutter/material.dart';

class SmartBedPalette {
  SmartBedPalette._();

  static const Color background = Color(0xFF0A1628);
  static const Color surfaceDark = Color(0xFF13213A);
  static const Color surfaceLight = Color(0xFF1A2740);
  static const Color accent = Color(0xFF00D4FF);
  static const Color secondaryAccent = Color(0xFF7B68EE);
  static const Color warmAccent = Color(0xFFFF6B35);
  static const Color gold = Color(0xFFFFD700);
  static const Color connected = Color(0xFF39D98A);
  static const Color warning = Color(0xFFF5A524);
  static const Color danger = Color(0xFFFF6B6B);
  static const Color bodyText = Color(0xFF9FB0CC);
  static const Color lightBackground = Color(0xFFF4F7FC);
  static const Color lightSurface = Color(0xFFFFFFFF);
  static const Color lightSurfaceAlt = Color(0xFFE9F0FB);
  static const Color lightText = Color(0xFF11203A);
  static const Color lightMuted = Color(0xFF62738E);

  static Color scaffold(Brightness brightness) =>
      brightness == Brightness.dark ? background : lightBackground;

  static Color surface(Brightness brightness) =>
      brightness == Brightness.dark ? surfaceDark : lightSurface;

  static Color surfaceAlt(Brightness brightness) =>
      brightness == Brightness.dark ? surfaceLight : lightSurfaceAlt;

  static Color body(Brightness brightness) =>
      brightness == Brightness.dark ? bodyText : lightMuted;

  static Color headline(Brightness brightness) =>
      brightness == Brightness.dark ? Colors.white : lightText;
}

ThemeData buildSmartBedTheme({Brightness brightness = Brightness.dark}) {
  final isDark = brightness == Brightness.dark;
  final scheme = ColorScheme.fromSeed(
    seedColor: SmartBedPalette.accent,
    brightness: brightness,
    primary: SmartBedPalette.accent,
    secondary: SmartBedPalette.secondaryAccent,
    tertiary: SmartBedPalette.warmAccent,
    surface: SmartBedPalette.surface(brightness),
  ).copyWith(
    onPrimary: isDark ? SmartBedPalette.background : Colors.white,
    onSecondary: Colors.white,
    onSurface: SmartBedPalette.headline(brightness),
    surfaceContainerHighest: SmartBedPalette.surfaceAlt(brightness),
    outline: SmartBedPalette.accent.withValues(alpha: isDark ? 0.18 : 0.12),
  );

  final base = ThemeData(
    useMaterial3: true,
    brightness: brightness,
    colorScheme: scheme,
    scaffoldBackgroundColor: SmartBedPalette.scaffold(brightness),
    canvasColor: SmartBedPalette.scaffold(brightness),
    fontFamilyFallback: const <String>[
      'Poppins',
      'Segoe UI',
      'Roboto',
      'Helvetica Neue',
      'Arial',
      'Noto Color Emoji',
    ],
  );

  TextStyle? headline(TextStyle? style) => style?.copyWith(
    color: SmartBedPalette.headline(brightness),
    fontWeight: FontWeight.w700,
    letterSpacing: 0.1,
  );

  TextStyle? body(TextStyle? style) => style?.copyWith(
    color: SmartBedPalette.body(brightness),
    height: 1.45,
  );

  return base.copyWith(
    appBarTheme: AppBarTheme(
      backgroundColor: Colors.transparent,
      foregroundColor: SmartBedPalette.headline(brightness),
      elevation: 0,
    ),
    cardTheme: CardThemeData(
      color: SmartBedPalette.surface(brightness),
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
    ),
    dividerColor: SmartBedPalette.accent.withValues(alpha: isDark ? 0.16 : 0.10),
    chipTheme: ChipThemeData(
      backgroundColor: SmartBedPalette.surfaceAlt(brightness),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      side: BorderSide(
        color: SmartBedPalette.accent.withValues(alpha: isDark ? 0.20 : 0.12),
      ),
      labelStyle: TextStyle(
        color: SmartBedPalette.headline(brightness),
        fontWeight: FontWeight.w600,
      ),
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 74,
      backgroundColor: SmartBedPalette.surface(brightness).withValues(
        alpha: isDark ? 0.94 : 0.98,
      ),
      indicatorColor: SmartBedPalette.accent.withValues(alpha: isDark ? 0.18 : 0.14),
      labelTextStyle: WidgetStateProperty.resolveWith<TextStyle?>(
        (states) => TextStyle(
          color: states.contains(WidgetState.selected)
              ? SmartBedPalette.headline(brightness)
              : SmartBedPalette.body(brightness),
          fontWeight: states.contains(WidgetState.selected)
              ? FontWeight.w700
              : FontWeight.w500,
        ),
      ),
      iconTheme: WidgetStateProperty.resolveWith<IconThemeData?>(
        (states) => IconThemeData(
          color: states.contains(WidgetState.selected)
              ? SmartBedPalette.accent
              : SmartBedPalette.body(brightness),
        ),
      ),
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
      ),
      titleLarge: headline(base.textTheme.titleLarge),
      titleMedium: headline(base.textTheme.titleMedium),
      titleSmall: headline(base.textTheme.titleSmall),
      bodyLarge: body(base.textTheme.bodyLarge),
      bodyMedium: body(base.textTheme.bodyMedium),
      bodySmall: body(base.textTheme.bodySmall),
      labelLarge: base.textTheme.labelLarge?.copyWith(
        color: SmartBedPalette.headline(brightness),
        fontWeight: FontWeight.w600,
      ),
      labelMedium: base.textTheme.labelMedium?.copyWith(
        color: SmartBedPalette.body(brightness),
      ),
      labelSmall: base.textTheme.labelSmall?.copyWith(
        color: SmartBedPalette.body(brightness),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: SmartBedPalette.surfaceAlt(brightness).withValues(
        alpha: isDark ? 0.82 : 0.95,
      ),
      labelStyle: TextStyle(color: SmartBedPalette.body(brightness)),
      hintStyle: TextStyle(
        color: SmartBedPalette.body(brightness).withValues(alpha: 0.84),
      ),
      prefixIconColor: SmartBedPalette.accent,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: BorderSide(
          color: SmartBedPalette.accent.withValues(alpha: isDark ? 0.18 : 0.10),
        ),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: BorderSide(
          color: SmartBedPalette.accent.withValues(alpha: isDark ? 0.18 : 0.10),
        ),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: BorderSide(
          color: SmartBedPalette.accent.withValues(alpha: isDark ? 0.65 : 0.35),
          width: 1.4,
        ),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: const BorderSide(color: SmartBedPalette.danger),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(18),
        borderSide: const BorderSide(color: SmartBedPalette.danger),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: SmartBedPalette.accent,
        foregroundColor: isDark ? SmartBedPalette.background : Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: SmartBedPalette.headline(brightness),
        side: BorderSide(
          color: SmartBedPalette.accent.withValues(alpha: isDark ? 0.32 : 0.18),
        ),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      ),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: ButtonStyle(
        backgroundColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return SmartBedPalette.accent.withValues(alpha: isDark ? 0.18 : 0.14);
          }
          return SmartBedPalette.surfaceAlt(brightness);
        }),
        foregroundColor: WidgetStatePropertyAll(
          SmartBedPalette.headline(brightness),
        ),
        side: WidgetStatePropertyAll(
          BorderSide(
            color: SmartBedPalette.accent.withValues(alpha: isDark ? 0.24 : 0.12),
          ),
        ),
      ),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: SmartBedPalette.accent,
    ),
    sliderTheme: base.sliderTheme.copyWith(
      activeTrackColor: SmartBedPalette.accent,
      inactiveTrackColor: SmartBedPalette.surfaceAlt(brightness),
      thumbColor: SmartBedPalette.secondaryAccent,
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return SmartBedPalette.accent;
        }
        return SmartBedPalette.body(brightness);
      }),
      trackColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return SmartBedPalette.accent.withValues(alpha: 0.36);
        }
        return SmartBedPalette.surfaceAlt(brightness);
      }),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: SmartBedPalette.surfaceAlt(brightness),
      contentTextStyle: TextStyle(color: SmartBedPalette.headline(brightness)),
    ),
  );
}

