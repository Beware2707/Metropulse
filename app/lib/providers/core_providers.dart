import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

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
    return repository.refreshIfStale();
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
