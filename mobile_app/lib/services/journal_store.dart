import 'package:hive_flutter/hive_flutter.dart';

class JournalStore {
  static const _boxName = 'sleep_journal';

  static Future<void> init() async {
    await Hive.initFlutter();
    await Hive.openBox(_boxName);
  }

  static Box get _box => Hive.box(_boxName);

  static Future<void> add(Map<String, dynamic> entry) async {
    await _box.add(entry);
  }

  static List<Map<String, dynamic>> readAll() {
    return _box.values
        .map((v) => Map<String, dynamic>.from(v as Map))
        .toList()
        .reversed
        .toList();
  }

  static Future<void> clear() async => _box.clear();
}