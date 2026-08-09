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

/// Hive-backed persistence: identity, settings, offline caches (stations,
/// favourites, journey history) and journey-session recovery state.
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

  /// The chosen UI language as a BCP-47 tag (e.g. 'en', 'hi'), or null when
  /// the user follows the system locale. Stored as the literal string 'system'
  /// (or absent) for the follow-system case so it round-trips cleanly.
  String? get localeTag {
    final raw = _box.get('locale');
    if (raw == null || raw == 'system') return null;
    return raw;
  }

  Future<void> saveLocaleTag(String? tag) =>
      _box.put('locale', tag ?? 'system');

  /// A user-chosen multiplier layered on top of the OS text-scale setting,
  /// for commuters who want the app larger than their system default.
  double get textScaleFactor => double.tryParse(_box.get('text_scale') ?? '') ?? 1.0;
  Future<void> saveTextScaleFactor(double scale) => _box.put('text_scale', '$scale');

  bool get highContrast => _box.get('high_contrast') == 'true';
  Future<void> setHighContrast(bool enabled) => _box.put('high_contrast', '$enabled');

  /// Material You (wallpaper-derived) colour scheme on supported devices.
  bool get dynamicColorEnabled => _box.get('dynamic_color') != 'false';
  Future<void> setDynamicColorEnabled(bool enabled) =>
      _box.put('dynamic_color', '$enabled');

  /// Step-free preference: the rider needs a lift-served path, not stairs.
  ///
  /// Persisted and app-wide on purpose. It began as local state on the
  /// planner screen, which meant a wheelchair user re-stated the need on
  /// every plan and Journey Mode never learned it at all — so the guidance
  /// that matters most, at the moment they are actually standing in the
  /// station, was the one place it could not reach.
  bool get stepFreePreferred => _box.get('step_free_preferred') == 'true';
  Future<void> setStepFreePreferred(bool enabled) =>
      _box.put('step_free_preferred', '$enabled');

  bool get notificationsEnabled => _box.get('notifications_enabled') != 'false';
  Future<void> setNotificationsEnabled(bool enabled) =>
      _box.put('notifications_enabled', '$enabled');

  /// Whether the rider has agreed to share anonymous usage analytics.
  ///
  /// Defaults to FALSE, and note the comparison direction: `== 'true'` means
  /// an absent or unreadable key resolves to "no". The notifications flag
  /// above uses `!= 'false'` because a missing preference there should mean
  /// "on"; here the same shape would silently opt every existing installed
  /// user into collection they were never asked about.
  bool get analyticsConsent => _box.get('analytics_consent') == 'true';
  Future<void> setAnalyticsConsent(bool granted) =>
      _box.put('analytics_consent', '$granted');

  /// True once the rider has actually been ASKED (either answer). Lets the
  /// app tell "declined" apart from "never prompted", so a future prompt
  /// doesn't nag someone who already said no.
  bool get analyticsConsentAsked => _box.get('analytics_consent_asked') == 'true';
  Future<void> setAnalyticsConsentAsked(bool asked) =>
      _box.put('analytics_consent_asked', '$asked');

  /// Whether the rider agreed to contribute station knowledge (which coach
  /// stops nearest which exit, and similar).
  ///
  /// Deliberately SEPARATE from [analyticsConsent]. Analytics is scoped so it
  /// cannot carry a destination — the privacy policy says in as many words
  /// that we do not receive which stations you travelled between. A coach-exit
  /// report is exactly that, about one station, and so it has to be its own
  /// decision. Folding it into the analytics toggle would quietly break a
  /// promise the rider already read.
  ///
  /// `== 'true'` so an absent key means no.
  bool get contributionConsent => _box.get('contribution_consent') == 'true';
  Future<void> setContributionConsent(bool granted) =>
      _box.put('contribution_consent', '$granted');

  bool get contributionConsentAsked =>
      _box.get('contribution_consent_asked') == 'true';
  Future<void> setContributionConsentAsked(bool asked) =>
      _box.put('contribution_consent_asked', '$asked');

  // -- notifications sync state -----------------------------------------------

  int get lastSeenNotificationId =>
      int.tryParse(_box.get('last_seen_notification_id') ?? '') ?? 0;
  Future<void> saveLastSeenNotificationId(int id) =>
      _box.put('last_seen_notification_id', '$id');

  // -- journey context ----------------------------------------------------------
  //
  // The backend owns the journey session; this stores the plan-derived extras
  // (interchanges, coach, exit, and the full plan snapshot so the GTFS-
  // timetable progress simulation can be rebuilt after a restart). Keyed by
  // journey id and cleared when a journey ends.

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

  // -- recent station searches ---------------------------------------------------

  static const _maxRecentSearches = 12;

  List<String> get recentSearchStopIds {
    final raw = _box.get('recent_searches');
    if (raw == null) return const [];
    try {
      return (jsonDecode(raw) as List<dynamic>).map((e) => '$e').toList(growable: false);
    } on FormatException {
      return const [];
    }
  }

  Future<void> recordSearchVisit(String stopId) async {
    final deduped = recentSearchStopIds.where((id) => id != stopId);
    final updated = [stopId, ...deduped].take(_maxRecentSearches).toList(growable: false);
    await _box.put('recent_searches', jsonEncode(updated));
  }

  Future<void> clearRecentSearches() => _box.delete('recent_searches');

  // -- pinned journeys (local-only shortcuts into the planner) --------------------

  List<Map<String, dynamic>> get pinnedJourneys {
    final raw = _box.get('pinned_journeys');
    if (raw == null) return const [];
    try {
      return (jsonDecode(raw) as List<dynamic>)
          .whereType<Map<String, dynamic>>()
          .toList(growable: false);
    } on FormatException {
      return const [];
    }
  }

  Future<void> addPinnedJourney({
    required String originStopId,
    required String destinationStopId,
    required String label,
  }) async {
    final updated = [
      ...pinnedJourneys,
      {
        'origin_stop_id': originStopId,
        'destination_stop_id': destinationStopId,
        'label': label,
      },
    ];
    await _box.put('pinned_journeys', jsonEncode(updated));
  }

  Future<void> removePinnedJourneyAt(int index) async {
    final updated = [...pinnedJourneys]..removeAt(index);
    await _box.put('pinned_journeys', jsonEncode(updated));
  }

  // -- dismissed save-journey prompts (per origin/destination pair) --------------

  List<String> get _dismissedSavePromptKeys {
    final raw = _box.get('dismissed_save_prompts');
    if (raw == null) return const [];
    try {
      return (jsonDecode(raw) as List<dynamic>).map((e) => '$e').toList(growable: false);
    } on FormatException {
      return const [];
    }
  }

  /// True once the rider has tapped "Not now" for this exact route before —
  /// so the arrival sheet stops re-asking for a route it already knows the
  /// answer to.
  bool hasDismissedSavePrompt({required String originStopId, required String destinationStopId}) =>
      _dismissedSavePromptKeys.contains('$originStopId>$destinationStopId');

  Future<void> dismissSavePrompt({required String originStopId, required String destinationStopId}) async {
    final key = '$originStopId>$destinationStopId';
    final existing = _dismissedSavePromptKeys;
    if (existing.contains(key)) return;
    await _box.put('dismissed_save_prompts', jsonEncode([...existing, key]));
  }

  // -- one-time hints ---------------------------------------------------------------

  bool get hasSeenMapHint => _box.get('has_seen_map_hint') == 'true';
  Future<void> markMapHintSeen() => _box.put('has_seen_map_hint', 'true');

  /// First-launch onboarding, shown once before the app's own splash-to-home
  /// flow ever reaches the home screen.
  bool get hasCompletedOnboarding => _box.get('has_completed_onboarding') == 'true';
  Future<void> markOnboardingCompleted() => _box.put('has_completed_onboarding', 'true');

  // -- offline station cache -----------------------------------------------------

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

  // -- favourites cache (offline fallback) ----------------------------------------

  List<Map<String, dynamic>>? get cachedFavouriteStations =>
      _decodeMapList(_box.get('favourites_cache'));

  Future<void> saveFavouriteStationsCache(List<Map<String, dynamic>> rows) =>
      _box.put('favourites_cache', jsonEncode(rows));

  // -- journey history cache (offline fallback) -----------------------------------

  List<Map<String, dynamic>>? get cachedJourneyHistory =>
      _decodeMapList(_box.get('journey_history_cache'));

  Future<void> saveJourneyHistoryCache(List<Map<String, dynamic>> rows) =>
      _box.put('journey_history_cache', jsonEncode(rows));

  List<Map<String, dynamic>>? _decodeMapList(String? raw) {
    if (raw == null) return null;
    try {
      return (jsonDecode(raw) as List<dynamic>)
          .whereType<Map<String, dynamic>>()
          .toList(growable: false);
    } on FormatException {
      return null;
    }
  }
}
