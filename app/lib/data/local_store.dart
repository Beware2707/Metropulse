import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive/hive.dart';
import 'package:uuid/uuid.dart';

import '../core/config.dart';
import '../domain/models/station.dart';

/// Riverpod handle; overridden with the opened store in main().
final localStoreProvider = Provider<LocalStore>(
  (ref) => throw UnimplementedError('LocalStore is provided in main()'),
);

/// Hive-backed persistence: identity, settings, and the offline station cache.
class LocalStore {
  LocalStore._(this._box);

  final Box<String> _box;

  static const _boxName = 'metropulse';

  static Future<LocalStore> open() async {
    final box = await Hive.openBox<String>(_boxName);
    return LocalStore._(box);
  }

  // -- identity ---------------------------------------------------------------

  String get deviceId {
    final existing = _box.get('device_id');
    if (existing != null) return existing;
    final generated = const Uuid().v4();
    _box.put('device_id', generated);
    return generated;
  }

  String? get token => _box.get('token');
  Future<void> saveToken(String token) => _box.put('token', token);
  Future<void> clearToken() => _box.delete('token');

  // -- settings ---------------------------------------------------------------

  String get apiBase => _box.get('api_base') ?? AppConfig.defaultApiBase;
  Future<void> saveApiBase(String value) => _box.put('api_base', value);

  String get themeMode => _box.get('theme_mode') ?? 'system';
  Future<void> saveThemeMode(String value) => _box.put('theme_mode', value);

  // -- journey context ----------------------------------------------------------
  //
  // The backend owns the journey session; this stores the plan-derived extras
  // (interchanges, coach, exit) so Journey Mode survives backgrounding and
  // full restarts. Keyed by journey id and cleared when a journey ends.

  Map<String, dynamic>? journeyContext(int journeyId) {
    final raw = _box.get('journey_ctx');
    if (raw == null) return null;
    try {
      final decoded = jsonDecode(raw) as Map<String, dynamic>;
      if (decoded['journey_id'] == journeyId) return decoded;
    } on FormatException {
      return null;
    }
    return null;
  }

  Future<void> saveJourneyContext(int journeyId, Map<String, dynamic> context) =>
      _box.put('journey_ctx', jsonEncode({...context, 'journey_id': journeyId}));

  Future<void> clearJourneyContext() => _box.delete('journey_ctx');

  // -- offline station cache ----------------------------------------------------

  OfflineBundle? get cachedBundle {
    final raw = _box.get('offline_bundle');
    if (raw == null) return null;
    try {
      return OfflineBundle.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } on FormatException {
      return null;
    }
  }

  String? get cachedBundleVersion => _box.get('offline_bundle_version');

  Future<void> saveBundle(OfflineBundle bundle, String rawJson) async {
    await _box.put('offline_bundle', rawJson);
    await _box.put('offline_bundle_version', bundle.version);
  }
}
