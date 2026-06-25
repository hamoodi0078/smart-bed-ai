// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Arabic (`ar`).
class AppLocalizationsAr extends AppLocalizations {
  AppLocalizationsAr([String locale = 'ar']) : super(locale);

  @override
  String get appTitle => 'سرير دانة الذكي';

  @override
  String get appTitleShort => 'دانة';

  @override
  String get greetingMorning => 'صباح الخير';

  @override
  String get greetingAfternoon => 'مساء الخير';

  @override
  String get greetingEvening => 'مساء النور';

  @override
  String get bedOnline => 'السرير متصل';

  @override
  String get bedOffline => 'السرير غير متصل';

  @override
  String get weeklySleepScore => 'تقييم النوم الأسبوعي';

  @override
  String get lastNight => 'الليلة الماضية';

  @override
  String get sleepScore => 'تقييم النوم';

  @override
  String get streak => 'سلسلة الأيام';

  @override
  String get danaActivity => 'نشاط دانة';

  @override
  String get keepUpGreatWork => 'أحسنت! واصل هذا النظام.';

  @override
  String get nextPrayer => 'الصلاة القادمة';

  @override
  String get prayerCalendar => 'تقويم الصلاة';

  @override
  String get todaysPrayers => 'صلوات اليوم';

  @override
  String get todaysHadith => 'حديث اليوم';

  @override
  String get sunnahTip => 'نصيحة سنّة الليلة';

  @override
  String get islamicMode => 'الوضع الإسلامي';

  @override
  String get ramadanKareem => 'رمضان كريم 🌙';

  @override
  String get prayerFajr => 'الفجر';

  @override
  String get prayerDhuhr => 'الظهر';

  @override
  String get prayerAsr => 'العصر';

  @override
  String get prayerMaghrib => 'المغرب';

  @override
  String get prayerIsha => 'العشاء';

  @override
  String get quickActionWindDown => 'الاسترخاء';

  @override
  String get quickActionLed => 'إضاءة LED';

  @override
  String get quickActionSpotify => 'سبوتيفاي';

  @override
  String get quickActionAlarms => 'المنبهات';

  @override
  String get quickActionScenes => 'المشاهد';

  @override
  String get quickActionDanaChat => 'محادثة دانة';

  @override
  String get quickActionAchievements => 'الإنجازات';

  @override
  String get quickActionJournal => 'يوميات النوم';

  @override
  String get quickActionHealth => 'الصحة';

  @override
  String updateAvailable(String version) {
    return 'تحديث متاح — v$version';
  }

  @override
  String get updateRequired => 'تحديث مطلوب';

  @override
  String get updateNow => 'تحديث الآن';

  @override
  String get updateLater => 'لاحقاً';

  @override
  String get retry => 'إعادة المحاولة';

  @override
  String get close => 'إغلاق';

  @override
  String get cancel => 'إلغاء';

  @override
  String get save => 'حفظ';

  @override
  String get errorConnectionTimeout => 'انتهت مهلة الاتصال. تحقق من شبكتك.';

  @override
  String get errorCannotReach => 'تعذر الوصول إلى الخادم. تحقق من شبكتك.';

  @override
  String get errorSessionExpired => 'انتهت الجلسة. يرجى تسجيل الدخول مرة أخرى.';

  @override
  String get errorNotAvailable => 'البيانات غير متاحة. اسحب للأسفل للمحاولة.';

  @override
  String get errorServer => 'خطأ في الخادم. يرجى المحاولة مرة أخرى.';

  @override
  String get errorDefault => 'تعذر تحميل البيانات. اسحب للأسفل للمحاولة.';

  @override
  String showingCachedData(String error) {
    return 'عرض البيانات المخزنة — $error';
  }

  @override
  String get peaceBeWithYou => 'السلام عليكم. هل أنت مستعد لليلة هانئة؟';

  @override
  String get danaGuideActive => 'دليل دانة · نشط';

  @override
  String get spotifyPauseNote => 'سيتوقف سبوتيفاي تلقائياً 🎵';

  @override
  String get ledPreview => 'معاينة الإضاءة';

  @override
  String get alarmTitle => 'المنبهات';

  @override
  String get addAlarm => 'إضافة منبه';

  @override
  String get editAlarm => 'تعديل المنبه';

  @override
  String get deleteAlarm => 'حذف المنبه';

  @override
  String get smartAlarm => 'منبه ذكي';

  @override
  String get alarmLabel => 'التسمية';

  @override
  String get alarmTime => 'الوقت';

  @override
  String get alarmRepeat => 'التكرار';

  @override
  String get scenesTitle => 'المشاهد';

  @override
  String get ledTitle => 'التحكم في الإضاءة';

  @override
  String get soundsTitle => 'أصوات النوم';

  @override
  String get partnerMode => 'وضع الشريك';

  @override
  String get partnerLinked => 'الشريك مرتبط';

  @override
  String get partnerNotLinked => 'لا يوجد شريك مرتبط';

  @override
  String get subscriptionTitle => 'الاشتراك';

  @override
  String get subscribePremium => 'الترقية إلى Premium';

  @override
  String get subscriptionFree => 'مجاني';

  @override
  String get subscriptionPremium => 'مميز';

  @override
  String get settingsTitle => 'الإعدادات';

  @override
  String get profileTitle => 'الملف الشخصي';

  @override
  String get sleepReport => 'تقرير النوم';

  @override
  String get weeklyReport => 'التقرير الأسبوعي';

  @override
  String get sleepTips => 'نصائح النوم';

  @override
  String get achievements => 'الإنجازات';

  @override
  String get journal => 'يوميات النوم';

  @override
  String get health => 'لوحة الصحة';

  @override
  String get connectBed => 'ربط السرير';

  @override
  String get bedConnected => 'السرير مرتبط';

  @override
  String get bedNotConnected => 'السرير غير مرتبط';

  @override
  String get scanQR => 'مسح رمز QR';

  @override
  String get onboardingWelcome => 'مرحباً بك في دانة';

  @override
  String get onboardingSubtitle => 'رفيقك الذكي للنوم';

  @override
  String get getStarted => 'ابدأ الآن';

  @override
  String get signIn => 'تسجيل الدخول';

  @override
  String get signOut => 'تسجيل الخروج';

  @override
  String get createAccount => 'إنشاء حساب';
}
