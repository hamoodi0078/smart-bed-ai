import 'package:hive_flutter/hive_flutter.dart';

class JournalStore {
  JournalStore._();

  static const String _boxName = 'sleep_journal';

  static Future<void> init() async {
    await Hive.initFlutter();
    await Hive.openBox<dynamic>(_boxName);
  }

  static Box<dynamic> get _box => Hive.box<dynamic>(_boxName);

  static Future<void> add(Map<String, dynamic> entry) async {
    await _box.add(entry);
  }

  static List<Map<String, dynamic>> readAll() {
    return _box.values
        .map((v) => Map<String, dynamic>.from(v as Map<dynamic, dynamic>))
        .toList()
        .reversed
        .toList();
  }

  static Future<void> clear() async => _box.clear();
}
