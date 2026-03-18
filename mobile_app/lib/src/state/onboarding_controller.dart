import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

final initialOnboardingCompletedProvider = Provider<bool>((ref) => false);

class OnboardingStore {
  OnboardingStore._();

  static const String _key = 'onboarding_completed_v1';

  static Future<bool> readCompleted() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_key) ?? false;
  }

  static Future<void> writeCompleted(bool completed) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_key, completed);
  }
}

final onboardingControllerProvider =
    NotifierProvider<OnboardingController, bool>(OnboardingController.new);

class OnboardingController extends Notifier<bool> {
  @override
  bool build() => ref.read(initialOnboardingCompletedProvider);

  Future<void> markCompleted() async {
    state = true;
    await OnboardingStore.writeCompleted(true);
  }
}
