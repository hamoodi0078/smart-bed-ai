import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _themeStorageKey = 'danah.theme_mode';

final themePreferenceStoreProvider = Provider<ThemePreferenceStore>(
  (ref) => const ThemePreferenceStore(),
);

final initialThemeModeProvider = Provider<ThemeMode>(
  (ref) => ThemeMode.system,
);

final themeControllerProvider =
    NotifierProvider<ThemeController, ThemeMode>(ThemeController.new);

class ThemePreferenceStore {
  const ThemePreferenceStore();

  static Future<ThemeMode> readInitialMode() async {
    final prefs = await SharedPreferences.getInstance();
    return _themeModeFromString(prefs.getString(_themeStorageKey));
  }

  Future<void> write(ThemeMode mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_themeStorageKey, _themeModeToString(mode));
  }
}

class ThemeController extends Notifier<ThemeMode> {
  ThemePreferenceStore get _store => ref.read(themePreferenceStoreProvider);

  @override
  ThemeMode build() => ref.read(initialThemeModeProvider);

  Future<void> setThemeMode(ThemeMode mode) async {
    if (state == mode) {
      return;
    }
    state = mode;
    await _store.write(mode);
  }

  Future<void> applyRemoteTheme(String value) async {
    final mode = _themeModeFromString(value);
    if (state == mode) {
      return;
    }
    state = mode;
    await _store.write(mode);
  }
}

ThemeMode _themeModeFromString(String? value) {
  switch ((value ?? '').trim().toLowerCase()) {
    case 'light':
      return ThemeMode.light;
    case 'dark':
      return ThemeMode.dark;
    default:
      return ThemeMode.system;
  }
}

String _themeModeToString(ThemeMode mode) {
  switch (mode) {
    case ThemeMode.light:
      return 'light';
    case ThemeMode.dark:
      return 'dark';
    case ThemeMode.system:
      return 'system';
  }
}

