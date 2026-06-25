// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Danah Smart Bed';

  @override
  String get appTitleShort => 'Danah';

  @override
  String get greetingMorning => 'Good Morning';

  @override
  String get greetingAfternoon => 'Good Afternoon';

  @override
  String get greetingEvening => 'Good Evening';

  @override
  String get bedOnline => 'Bed Online';

  @override
  String get bedOffline => 'Bed Offline';

  @override
  String get weeklySleepScore => 'Weekly Sleep Score';

  @override
  String get lastNight => 'Last Night';

  @override
  String get sleepScore => 'Sleep Score';

  @override
  String get streak => 'Streak';

  @override
  String get danaActivity => 'Dana Activity';

  @override
  String get keepUpGreatWork => 'Keep up the great work!';

  @override
  String get nextPrayer => 'Next Prayer';

  @override
  String get prayerCalendar => 'Prayer Calendar';

  @override
  String get todaysPrayers => 'Today\'s Prayers';

  @override
  String get todaysHadith => 'Today\'s Hadith';

  @override
  String get sunnahTip => 'Tonight\'s Sunnah Tip';

  @override
  String get islamicMode => 'Islamic Mode';

  @override
  String get ramadanKareem => 'Ramadan Kareem 🌙';

  @override
  String get prayerFajr => 'Fajr';

  @override
  String get prayerDhuhr => 'Dhuhr';

  @override
  String get prayerAsr => 'Asr';

  @override
  String get prayerMaghrib => 'Maghrib';

  @override
  String get prayerIsha => 'Isha';

  @override
  String get quickActionWindDown => 'Wind-Down';

  @override
  String get quickActionLed => 'LED Control';

  @override
  String get quickActionSpotify => 'Spotify';

  @override
  String get quickActionAlarms => 'Alarms';

  @override
  String get quickActionScenes => 'Scenes';

  @override
  String get quickActionDanaChat => 'Dana Chat';

  @override
  String get quickActionAchievements => 'Achievements';

  @override
  String get quickActionJournal => 'Journal';

  @override
  String get quickActionHealth => 'Health';

  @override
  String updateAvailable(String version) {
    return 'Update available — v$version';
  }

  @override
  String get updateRequired => 'Update Required';

  @override
  String get updateNow => 'Update Now';

  @override
  String get updateLater => 'Later';

  @override
  String get retry => 'Retry';

  @override
  String get close => 'Close';

  @override
  String get cancel => 'Cancel';

  @override
  String get save => 'Save';

  @override
  String get errorConnectionTimeout =>
      'Connection timed out. Check your network.';

  @override
  String get errorCannotReach => 'Cannot reach the server. Check your network.';

  @override
  String get errorSessionExpired => 'Session expired. Please sign in again.';

  @override
  String get errorNotAvailable => 'Data not available. Pull down to retry.';

  @override
  String get errorServer => 'Server error. Please try again later.';

  @override
  String get errorDefault => 'Could not load data. Pull down to retry.';

  @override
  String showingCachedData(String error) {
    return 'Showing cached data — $error';
  }

  @override
  String get peaceBeWithYou => 'Peace be with you. Ready for a restful night?';

  @override
  String get danaGuideActive => 'Dana Guide · Active';

  @override
  String get spotifyPauseNote => 'Spotify will pause automatically 🎵';

  @override
  String get ledPreview => 'LED Preview';

  @override
  String get alarmTitle => 'Alarms';

  @override
  String get addAlarm => 'Add Alarm';

  @override
  String get editAlarm => 'Edit Alarm';

  @override
  String get deleteAlarm => 'Delete Alarm';

  @override
  String get smartAlarm => 'Smart Alarm';

  @override
  String get alarmLabel => 'Label';

  @override
  String get alarmTime => 'Time';

  @override
  String get alarmRepeat => 'Repeat';

  @override
  String get scenesTitle => 'Scenes';

  @override
  String get ledTitle => 'LED Control';

  @override
  String get soundsTitle => 'Sleep Sounds';

  @override
  String get partnerMode => 'Partner Mode';

  @override
  String get partnerLinked => 'Partner Linked';

  @override
  String get partnerNotLinked => 'No Partner Linked';

  @override
  String get subscriptionTitle => 'Subscription';

  @override
  String get subscribePremium => 'Go Premium';

  @override
  String get subscriptionFree => 'Free';

  @override
  String get subscriptionPremium => 'Premium';

  @override
  String get settingsTitle => 'Settings';

  @override
  String get profileTitle => 'Profile';

  @override
  String get sleepReport => 'Sleep Report';

  @override
  String get weeklyReport => 'Weekly Report';

  @override
  String get sleepTips => 'Sleep Tips';

  @override
  String get achievements => 'Achievements';

  @override
  String get journal => 'Sleep Journal';

  @override
  String get health => 'Health Dashboard';

  @override
  String get connectBed => 'Connect Bed';

  @override
  String get bedConnected => 'Bed Connected';

  @override
  String get bedNotConnected => 'Bed Not Connected';

  @override
  String get scanQR => 'Scan QR Code';

  @override
  String get onboardingWelcome => 'Welcome to Danah';

  @override
  String get onboardingSubtitle => 'Your AI-powered sleep companion';

  @override
  String get getStarted => 'Get Started';

  @override
  String get signIn => 'Sign In';

  @override
  String get signOut => 'Sign Out';

  @override
  String get createAccount => 'Create Account';
}
