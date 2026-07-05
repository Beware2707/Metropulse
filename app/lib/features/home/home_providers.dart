import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/location_service.dart';
import '../../data/repositories.dart';
import '../../domain/models/commute_card.dart';
import '../../domain/models/journey.dart';
import '../../domain/nearby.dart';
import '../../providers/core_providers.dart';

final commuteCardProvider = FutureProvider<CommuteCard?>(
  (ref) => ref.watch(commuteRepositoryProvider).card(),
);

final activeJourneyProvider = FutureProvider<Journey?>(
  (ref) => ref.watch(journeyRepositoryProvider).current(),
);

final recentJourneysProvider = FutureProvider<List<Journey>>((ref) async {
  final journeys = await ref.watch(journeyRepositoryProvider).history(limit: 5);
  return journeys.where((j) => j.status != 'active').toList(growable: false);
});

final alertsRepositoryProvider = Provider<AlertsRepository>(
  (ref) => AlertsRepository(ref.watch(apiClientProvider)),
);

final activeAlertsProvider = FutureProvider<List<Map<String, dynamic>>>(
  (ref) => ref.watch(alertsRepositoryProvider).active(),
);

final favouriteStationsProvider = FutureProvider<List<Map<String, dynamic>>>(
  (ref) => ref.watch(favouritesRepositoryProvider).list(),
);

/// Last train tonight from the user's Home (or first favourite) station.
final homeLastTrainProvider =
    FutureProvider<Map<String, dynamic>?>((ref) async {
  final favourites = await ref.watch(favouriteStationsProvider.future);
  if (favourites.isEmpty) return null;
  final home = favourites.firstWhere(
    (f) => '${f['label']}'.toLowerCase() == 'home',
    orElse: () => favourites.first,
  );
  final stopId = '${home['stop_id']}';
  final info =
      await ref.watch(stationsRepositoryProvider).lastTrain(stopId);
  return info == null ? null : {...info, 'stop_id': stopId};
});

final locationServiceProvider =
    Provider<LocationService>((ref) => const LocationService());

sealed class NearbyState {
  const NearbyState();
}

class NearbyReady extends NearbyState {
  const NearbyReady(this.stations);
  final List<NearbyStation> stations;
}

class NearbyNeedsPermission extends NearbyState {
  const NearbyNeedsPermission();
}

class NearbyUnavailable extends NearbyState {
  const NearbyUnavailable();
}

/// Nearest stations from the offline bundle + one low-accuracy location fix.
final nearbyStationsProvider = FutureProvider<NearbyState>((ref) async {
  final bundle = ref.watch(offlineBundleProvider).valueOrNull;
  if (bundle == null || bundle.stations.isEmpty) {
    return const NearbyUnavailable();
  }
  final result =
      await ref.watch(locationServiceProvider).currentPosition();
  return switch (result) {
    LocationFix(:final lat, :final lon) =>
      NearbyReady(nearestStations(bundle.stations, lat, lon)),
    LocationDenied() => const NearbyNeedsPermission(),
    LocationUnavailable() => const NearbyUnavailable(),
  };
});
