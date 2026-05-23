import 'dart:ui' show Locale;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _kLocaleKey = 'app_locale';
const _supportedLocales = ['en', 'ar'];

final localeControllerProvider =
    StateNotifierProvider<LocaleController, Locale>((ref) {
  return LocaleController();
});

class LocaleController extends StateNotifier<Locale> {
  LocaleController() : super(const Locale('en')) {
    _loadSaved();
  }

  Future<void> _loadSaved() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_kLocaleKey);
    if (saved != null && _supportedLocales.contains(saved)) {
      state = Locale(saved);
    }
  }

  Future<void> setLocale(Locale locale) async {
    if (!_supportedLocales.contains(locale.languageCode)) return;
    state = locale;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kLocaleKey, locale.languageCode);
  }

  void toggleArabic() {
    if (state.languageCode == 'ar') {
      setLocale(const Locale('en'));
    } else {
      setLocale(const Locale('ar'));
    }
  }
}

/// Convenience provider for the current language code (e.g. 'en' or 'ar').
final localeLangProvider = Provider<String>((ref) {
  return ref.watch(localeControllerProvider).languageCode;
});

/// True when the app is currently displaying Arabic.
final isArabicProvider = Provider<bool>((ref) {
  return ref.watch(localeLangProvider) == 'ar';
});
