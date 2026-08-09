import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/analytics.dart';
import '../data/api_client.dart';
import '../data/local_store.dart';
import '../data/repositories.dart';
import '../domain/models/station.dart';

export '../data/local_store.dart' show localStoreProvider;

final apiClientProvider = Provider<ApiClient>(
  (ref) => ApiClient(ref.watch(localStoreProvider)),
);

final stationsRepositoryProvider = Provider<StationsRepository>(
  (ref) => StationsRepository(
    ref.watch(apiClientProvider),
    ref.watch(localStoreProvider),
  ),
);

final trainsRepositoryProvider = Provider<TrainsRepository>(
  (ref) => TrainsRepository(ref.watch(apiClientProvider)),
);

final journeyRepositoryProvider = Provider<JourneyRepository>(
  (ref) => JourneyRepository(ref.watch(apiClientProvider), ref.watch(localStoreProvider)),
);

final favouritesRepositoryProvider = Provider<FavouritesRepository>(
  (ref) => FavouritesRepository(ref.watch(apiClientProvider), ref.watch(localStoreProvider)),
);

final commuteRepositoryProvider = Provider<CommuteRepository>(
  (ref) => CommuteRepository(ref.watch(apiClientProvider)),
);

final intelligenceRepositoryProvider = Provider<IntelligenceRepository>(
  (ref) => IntelligenceRepository(ref.watch(apiClientProvider)),
);

final notificationsRepositoryProvider = Provider<NotificationsRepository>(
  (ref) => NotificationsRepository(ref.watch(apiClientProvider)),
);

final destinationAlertsRepositoryProvider = Provider<DestinationAlertsRepository>(
  (ref) => DestinationAlertsRepository(ref.watch(apiClientProvider)),
);

final remindersRepositoryProvider = Provider<RemindersRepository>(
  (ref) => RemindersRepository(ref.watch(apiClientProvider)),
);

final replayRepositoryProvider = Provider<ReplayRepository>(
  (ref) => ReplayRepository(ref.watch(apiClientProvider)),
);

final feedbackRepositoryProvider = Provider<FeedbackRepository>(
  (ref) => FeedbackRepository(ref.watch(apiClientProvider)),
);

final analyticsRepositoryProvider = Provider<AnalyticsRepository>(
  (ref) => AnalyticsRepository(ref.watch(apiClientProvider)),
);

final serviceDayRepositoryProvider = Provider<ServiceDayRepository>(
  (ref) => ServiceDayRepository(ref.watch(apiClientProvider)),
);

final contributionRepositoryProvider = Provider<ContributionRepository>(
  (ref) => ContributionRepository(ref.watch(apiClientProvider)),
);

/// True/false when the server could answer, null while loading or offline.
///
/// Kept alive: the answer changes at most once a day, and re-asking on every
/// empty board would be pure noise.
final hasTimetableTodayProvider = FutureProvider<bool?>((ref) async {
  ref.keepAlive();
  return ref.watch(serviceDayRepositoryProvider).hasTimetableToday();
});

/// The app-wide analytics emitter.
///
/// Reads consent through `ref.read` at emit time rather than capturing it
/// once: a rider who turns analytics off in Settings must stop being recorded
/// immediately, not at the next app launch. The service also drops anything
/// already buffered when it finds consent gone (see [AnalyticsService.flush]).
///
/// Not `autoDispose` — this outlives every screen by design, and disposing it
/// mid-session would silently drop the buffer.
final analyticsServiceProvider = Provider<AnalyticsService>((ref) {
  final repository = ref.watch(analyticsRepositoryProvider);
  final service = AnalyticsService(
    uploader: repository.upload,
    consentGranted: () => ref.read(localStoreProvider).analyticsConsent,
  );
  ref.onDispose(service.dispose);
  return service;
});

/// True when the OS reports an active network path — proactive, unlike
/// every other offline signal in this app (an HTTP call's own 8s/15s
/// timeout, the WebSocket's 60s reconnect watchdog), which only find out
/// something's wrong after already trying and failing.
final isOnlineProvider = StreamProvider<bool>((ref) async* {
  final connectivity = Connectivity();
  final initial = await connectivity.checkConnectivity();
  yield !initial.contains(ConnectivityResult.none);
  yield* connectivity.onConnectivityChanged.map(
    (results) => !results.contains(ConnectivityResult.none),
  );
});

/// The offline bundle: cached copy first, silently refreshed when stale.
final offlineBundleProvider =
    AsyncNotifierProvider<OfflineBundleNotifier, OfflineBundle?>(
  OfflineBundleNotifier.new,
);

class OfflineBundleNotifier extends AsyncNotifier<OfflineBundle?> {
  @override
  Future<OfflineBundle?> build() async {
    final repository = ref.watch(stationsRepositoryProvider);
    final cached = repository.cached;
    if (cached != null) {
      // Serve the cache now; refresh in the background without blocking UI.
      Future<void>.microtask(() async {
        final fresh = await repository.refreshIfStale();
        if (fresh != null && fresh != cached) state = AsyncData(fresh);
      });
      return cached;
    }
    // First-ever install: there's nothing to show yet, so this genuinely has
    // to wait on the network — but bounded well below Dio's own 8s/15s
    // timeouts, so a bad connection can't leave the splash screen hanging
    // for 20+ seconds before falling through to an empty state.
    try {
      return await repository.refreshIfStale().timeout(const Duration(seconds: 6));
    } on TimeoutException {
      return null;
    }
  }
}

/// Fast station lookup by id, derived from the bundle.
final stationIndexProvider = Provider<Map<String, Station>>((ref) {
  final bundle = ref.watch(offlineBundleProvider).valueOrNull;
  if (bundle == null) return const {};
  return {for (final station in bundle.stations) station.stopId: station};
});

/// Theme mode, persisted in Hive.
final themeModeProvider = NotifierProvider<ThemeModeNotifier, ThemeMode>(
  ThemeModeNotifier.new,
);

class ThemeModeNotifier extends Notifier<ThemeMode> {
  @override
  ThemeMode build() => switch (ref.watch(localStoreProvider).themeMode) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };

  Future<void> setMode(ThemeMode mode) async {
    state = mode;
    await ref.read(localStoreProvider).saveThemeMode(mode.name);
  }
}

/// The chosen UI locale, persisted in Hive. `null` means "follow the system
/// locale" — MaterialApp then resolves against `supportedLocales`.
final localeProvider = NotifierProvider<LocaleNotifier, Locale?>(
  LocaleNotifier.new,
);

class LocaleNotifier extends Notifier<Locale?> {
  @override
  Locale? build() {
    final tag = ref.watch(localStoreProvider).localeTag;
    return tag == null ? null : Locale(tag);
  }

  /// Sets the chosen locale; pass `null` to follow the system locale.
  Future<void> setLocale(Locale? locale) async {
    state = locale;
    await ref.read(localStoreProvider).saveLocaleTag(locale?.languageCode);
  }
}
