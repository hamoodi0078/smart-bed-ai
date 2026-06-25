import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_ar.dart';
import 'app_localizations_en.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('ar'),
    Locale('en'),
  ];

  /// No description provided for @appTitle.
  ///
  /// In en, this message translates to:
  /// **'Danah Smart Bed'**
  String get appTitle;

  /// No description provided for @appTitleShort.
  ///
  /// In en, this message translates to:
  /// **'Danah'**
  String get appTitleShort;

  /// No description provided for @greetingMorning.
  ///
  /// In en, this message translates to:
  /// **'Good Morning'**
  String get greetingMorning;

  /// No description provided for @greetingAfternoon.
  ///
  /// In en, this message translates to:
  /// **'Good Afternoon'**
  String get greetingAfternoon;

  /// No description provided for @greetingEvening.
  ///
  /// In en, this message translates to:
  /// **'Good Evening'**
  String get greetingEvening;

  /// No description provided for @bedOnline.
  ///
  /// In en, this message translates to:
  /// **'Bed Online'**
  String get bedOnline;

  /// No description provided for @bedOffline.
  ///
  /// In en, this message translates to:
  /// **'Bed Offline'**
  String get bedOffline;

  /// No description provided for @weeklySleepScore.
  ///
  /// In en, this message translates to:
  /// **'Weekly Sleep Score'**
  String get weeklySleepScore;

  /// No description provided for @lastNight.
  ///
  /// In en, this message translates to:
  /// **'Last Night'**
  String get lastNight;

  /// No description provided for @sleepScore.
  ///
  /// In en, this message translates to:
  /// **'Sleep Score'**
  String get sleepScore;

  /// No description provided for @streak.
  ///
  /// In en, this message translates to:
  /// **'Streak'**
  String get streak;

  /// No description provided for @danaActivity.
  ///
  /// In en, this message translates to:
  /// **'Dana Activity'**
  String get danaActivity;

  /// No description provided for @keepUpGreatWork.
  ///
  /// In en, this message translates to:
  /// **'Keep up the great work!'**
  String get keepUpGreatWork;

  /// No description provided for @nextPrayer.
  ///
  /// In en, this message translates to:
  /// **'Next Prayer'**
  String get nextPrayer;

  /// No description provided for @prayerCalendar.
  ///
  /// In en, this message translates to:
  /// **'Prayer Calendar'**
  String get prayerCalendar;

  /// No description provided for @todaysPrayers.
  ///
  /// In en, this message translates to:
  /// **'Today\'s Prayers'**
  String get todaysPrayers;

  /// No description provided for @todaysHadith.
  ///
  /// In en, this message translates to:
  /// **'Today\'s Hadith'**
  String get todaysHadith;

  /// No description provided for @sunnahTip.
  ///
  /// In en, this message translates to:
  /// **'Tonight\'s Sunnah Tip'**
  String get sunnahTip;

  /// No description provided for @islamicMode.
  ///
  /// In en, this message translates to:
  /// **'Islamic Mode'**
  String get islamicMode;

  /// No description provided for @ramadanKareem.
  ///
  /// In en, this message translates to:
  /// **'Ramadan Kareem 🌙'**
  String get ramadanKareem;

  /// No description provided for @prayerFajr.
  ///
  /// In en, this message translates to:
  /// **'Fajr'**
  String get prayerFajr;

  /// No description provided for @prayerDhuhr.
  ///
  /// In en, this message translates to:
  /// **'Dhuhr'**
  String get prayerDhuhr;

  /// No description provided for @prayerAsr.
  ///
  /// In en, this message translates to:
  /// **'Asr'**
  String get prayerAsr;

  /// No description provided for @prayerMaghrib.
  ///
  /// In en, this message translates to:
  /// **'Maghrib'**
  String get prayerMaghrib;

  /// No description provided for @prayerIsha.
  ///
  /// In en, this message translates to:
  /// **'Isha'**
  String get prayerIsha;

  /// No description provided for @quickActionWindDown.
  ///
  /// In en, this message translates to:
  /// **'Wind-Down'**
  String get quickActionWindDown;

  /// No description provided for @quickActionLed.
  ///
  /// In en, this message translates to:
  /// **'LED Control'**
  String get quickActionLed;

  /// No description provided for @quickActionSpotify.
  ///
  /// In en, this message translates to:
  /// **'Spotify'**
  String get quickActionSpotify;

  /// No description provided for @quickActionAlarms.
  ///
  /// In en, this message translates to:
  /// **'Alarms'**
  String get quickActionAlarms;

  /// No description provided for @quickActionScenes.
  ///
  /// In en, this message translates to:
  /// **'Scenes'**
  String get quickActionScenes;

  /// No description provided for @quickActionDanaChat.
  ///
  /// In en, this message translates to:
  /// **'Dana Chat'**
  String get quickActionDanaChat;

  /// No description provided for @quickActionAchievements.
  ///
  /// In en, this message translates to:
  /// **'Achievements'**
  String get quickActionAchievements;

  /// No description provided for @quickActionJournal.
  ///
  /// In en, this message translates to:
  /// **'Journal'**
  String get quickActionJournal;

  /// No description provided for @quickActionHealth.
  ///
  /// In en, this message translates to:
  /// **'Health'**
  String get quickActionHealth;

  /// No description provided for @updateAvailable.
  ///
  /// In en, this message translates to:
  /// **'Update available — v{version}'**
  String updateAvailable(String version);

  /// No description provided for @updateRequired.
  ///
  /// In en, this message translates to:
  /// **'Update Required'**
  String get updateRequired;

  /// No description provided for @updateNow.
  ///
  /// In en, this message translates to:
  /// **'Update Now'**
  String get updateNow;

  /// No description provided for @updateLater.
  ///
  /// In en, this message translates to:
  /// **'Later'**
  String get updateLater;

  /// No description provided for @retry.
  ///
  /// In en, this message translates to:
  /// **'Retry'**
  String get retry;

  /// No description provided for @close.
  ///
  /// In en, this message translates to:
  /// **'Close'**
  String get close;

  /// No description provided for @cancel.
  ///
  /// In en, this message translates to:
  /// **'Cancel'**
  String get cancel;

  /// No description provided for @save.
  ///
  /// In en, this message translates to:
  /// **'Save'**
  String get save;

  /// No description provided for @errorConnectionTimeout.
  ///
  /// In en, this message translates to:
  /// **'Connection timed out. Check your network.'**
  String get errorConnectionTimeout;

  /// No description provided for @errorCannotReach.
  ///
  /// In en, this message translates to:
  /// **'Cannot reach the server. Check your network.'**
  String get errorCannotReach;

  /// No description provided for @errorSessionExpired.
  ///
  /// In en, this message translates to:
  /// **'Session expired. Please sign in again.'**
  String get errorSessionExpired;

  /// No description provided for @errorNotAvailable.
  ///
  /// In en, this message translates to:
  /// **'Data not available. Pull down to retry.'**
  String get errorNotAvailable;

  /// No description provided for @errorServer.
  ///
  /// In en, this message translates to:
  /// **'Server error. Please try again later.'**
  String get errorServer;

  /// No description provided for @errorDefault.
  ///
  /// In en, this message translates to:
  /// **'Could not load data. Pull down to retry.'**
  String get errorDefault;

  /// No description provided for @showingCachedData.
  ///
  /// In en, this message translates to:
  /// **'Showing cached data — {error}'**
  String showingCachedData(String error);

  /// No description provided for @peaceBeWithYou.
  ///
  /// In en, this message translates to:
  /// **'Peace be with you. Ready for a restful night?'**
  String get peaceBeWithYou;

  /// No description provided for @danaGuideActive.
  ///
  /// In en, this message translates to:
  /// **'Dana Guide · Active'**
  String get danaGuideActive;

  /// No description provided for @spotifyPauseNote.
  ///
  /// In en, this message translates to:
  /// **'Spotify will pause automatically 🎵'**
  String get spotifyPauseNote;

  /// No description provided for @ledPreview.
  ///
  /// In en, this message translates to:
  /// **'LED Preview'**
  String get ledPreview;

  /// No description provided for @alarmTitle.
  ///
  /// In en, this message translates to:
  /// **'Alarms'**
  String get alarmTitle;

  /// No description provided for @addAlarm.
  ///
  /// In en, this message translates to:
  /// **'Add Alarm'**
  String get addAlarm;

  /// No description provided for @editAlarm.
  ///
  /// In en, this message translates to:
  /// **'Edit Alarm'**
  String get editAlarm;

  /// No description provided for @deleteAlarm.
  ///
  /// In en, this message translates to:
  /// **'Delete Alarm'**
  String get deleteAlarm;

  /// No description provided for @smartAlarm.
  ///
  /// In en, this message translates to:
  /// **'Smart Alarm'**
  String get smartAlarm;

  /// No description provided for @alarmLabel.
  ///
  /// In en, this message translates to:
  /// **'Label'**
  String get alarmLabel;

  /// No description provided for @alarmTime.
  ///
  /// In en, this message translates to:
  /// **'Time'**
  String get alarmTime;

  /// No description provided for @alarmRepeat.
  ///
  /// In en, this message translates to:
  /// **'Repeat'**
  String get alarmRepeat;

  /// No description provided for @scenesTitle.
  ///
  /// In en, this message translates to:
  /// **'Scenes'**
  String get scenesTitle;

  /// No description provided for @ledTitle.
  ///
  /// In en, this message translates to:
  /// **'LED Control'**
  String get ledTitle;

  /// No description provided for @soundsTitle.
  ///
  /// In en, this message translates to:
  /// **'Sleep Sounds'**
  String get soundsTitle;

  /// No description provided for @partnerMode.
  ///
  /// In en, this message translates to:
  /// **'Partner Mode'**
  String get partnerMode;

  /// No description provided for @partnerLinked.
  ///
  /// In en, this message translates to:
  /// **'Partner Linked'**
  String get partnerLinked;

  /// No description provided for @partnerNotLinked.
  ///
  /// In en, this message translates to:
  /// **'No Partner Linked'**
  String get partnerNotLinked;

  /// No description provided for @subscriptionTitle.
  ///
  /// In en, this message translates to:
  /// **'Subscription'**
  String get subscriptionTitle;

  /// No description provided for @subscribePremium.
  ///
  /// In en, this message translates to:
  /// **'Go Premium'**
  String get subscribePremium;

  /// No description provided for @subscriptionFree.
  ///
  /// In en, this message translates to:
  /// **'Free'**
  String get subscriptionFree;

  /// No description provided for @subscriptionPremium.
  ///
  /// In en, this message translates to:
  /// **'Premium'**
  String get subscriptionPremium;

  /// No description provided for @settingsTitle.
  ///
  /// In en, this message translates to:
  /// **'Settings'**
  String get settingsTitle;

  /// No description provided for @profileTitle.
  ///
  /// In en, this message translates to:
  /// **'Profile'**
  String get profileTitle;

  /// No description provided for @sleepReport.
  ///
  /// In en, this message translates to:
  /// **'Sleep Report'**
  String get sleepReport;

  /// No description provided for @weeklyReport.
  ///
  /// In en, this message translates to:
  /// **'Weekly Report'**
  String get weeklyReport;

  /// No description provided for @sleepTips.
  ///
  /// In en, this message translates to:
  /// **'Sleep Tips'**
  String get sleepTips;

  /// No description provided for @achievements.
  ///
  /// In en, this message translates to:
  /// **'Achievements'**
  String get achievements;

  /// No description provided for @journal.
  ///
  /// In en, this message translates to:
  /// **'Sleep Journal'**
  String get journal;

  /// No description provided for @health.
  ///
  /// In en, this message translates to:
  /// **'Health Dashboard'**
  String get health;

  /// No description provided for @connectBed.
  ///
  /// In en, this message translates to:
  /// **'Connect Bed'**
  String get connectBed;

  /// No description provided for @bedConnected.
  ///
  /// In en, this message translates to:
  /// **'Bed Connected'**
  String get bedConnected;

  /// No description provided for @bedNotConnected.
  ///
  /// In en, this message translates to:
  /// **'Bed Not Connected'**
  String get bedNotConnected;

  /// No description provided for @scanQR.
  ///
  /// In en, this message translates to:
  /// **'Scan QR Code'**
  String get scanQR;

  /// No description provided for @onboardingWelcome.
  ///
  /// In en, this message translates to:
  /// **'Welcome to Danah'**
  String get onboardingWelcome;

  /// No description provided for @onboardingSubtitle.
  ///
  /// In en, this message translates to:
  /// **'Your AI-powered sleep companion'**
  String get onboardingSubtitle;

  /// No description provided for @getStarted.
  ///
  /// In en, this message translates to:
  /// **'Get Started'**
  String get getStarted;

  /// No description provided for @signIn.
  ///
  /// In en, this message translates to:
  /// **'Sign In'**
  String get signIn;

  /// No description provided for @signOut.
  ///
  /// In en, this message translates to:
  /// **'Sign Out'**
  String get signOut;

  /// No description provided for @createAccount.
  ///
  /// In en, this message translates to:
  /// **'Create Account'**
  String get createAccount;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['ar', 'en'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'ar':
      return AppLocalizationsAr();
    case 'en':
      return AppLocalizationsEn();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
