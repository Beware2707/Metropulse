import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/config.dart';
import '../../data/air_quality_service.dart';
import '../../data/location_service.dart';
import '../../data/repositories.dart';
import '../../data/weather_service.dart';
import '../../domain/crowding.dart';
import '../../domain/models/commute_card.dart';
import '../../domain/models/intelligence.dart';
import '../../domain/models/journey.dart';
import '../../domain/nearby.dart';
import '../../providers/core_providers.dart';

final commuteCardProvider = FutureProvider<CommuteCard?>(
  (ref) => ref.watch(commuteRepositoryProvider).card(),
);

/// The commute Metro Intelligence predicts the user is about to make, learned
/// from their own journey history. Null while there isn't enough history yet
/// (not an error — just nothing learned so far).
final commutePredictionProvider = FutureProvider<CommutePrediction?>(
  (ref) => ref.watch(intelligenceRepositoryProvider).commutePrediction(),
);

/// Place roles (Home, a regular weekday destination) Metro Intelligence has
/// inferred from journey history — suggestions for Favourites to offer, not
/// facts to write on the user's behalf. Empty while nothing's been learned.
final inferredPlacesProvider = FutureProvider<List<InferredPlace>>(
  (ref) => ref.watch(intelligenceRepositoryProvider).inferredPlaces(),
);

/// A full route plan for the commute card's origin/destination, purely to
/// surface fare + a richer duration breakdown on Home — the card endpoint
/// itself only returns aggregate timing, not a fare-computable plan.
final homeSuggestedPlanProvider = FutureProvider<JourneyPlan?>((ref) async {
  final card = await ref.watch(commuteCardProvider.future);
  if (card == null) return null;
  try {
    return await ref
        .watch(journeyRepositoryProvider)
        .plan(card.originStopId, card.destinationStopId);
  } on Exception {
    return null; // the commute card itself already conveys the essentials
  }
});

/// The historical, route-and-hour-of-day delay estimate for the commute's
/// first ride leg — the only honest "will I be late" signal available
/// before a journey has actually started (a live per-vehicle delay only
/// exists once a real train is being tracked). Null when there's no ride leg
/// to estimate for.
final commuteDelayEstimateProvider = FutureProvider<DelayEstimate?>((ref) async {
  final plan = await ref.watch(homeSuggestedPlanProvider.future);
  final firstRide = plan?.legs.where((leg) => leg.isRide).firstOrNull;
  if (firstRide?.routeId == null) return null;
  return ref.watch(intelligenceRepositoryProvider).delayEstimate(
        routeId: firstRide!.routeId!,
        directionId: firstRide.directionId,
      );
});

/// Why Metro Intelligence recommends this coach for the commute — reused
/// straight from the existing coach-recommendation endpoint's own `reasons`
/// list (e.g. "typically less crowded", "short walk to a destination
/// exit"), never an invented caption. Empty when there's nothing to explain.
final homeCoachReasonsProvider = FutureProvider<List<String>>((ref) async {
  final card = await ref.watch(commuteCardProvider.future);
  if (card == null) return const [];
  final plan = await ref.watch(homeSuggestedPlanProvider.future);
  final firstRide = plan?.legs.where((leg) => leg.isRide).firstOrNull;
  final coach = await ref.watch(journeyRepositoryProvider).coachRecommendation(
        origin: card.originStopId,
        destination: card.destinationStopId,
        routeId: firstRide?.routeId,
        directionId: firstRide?.directionId,
      );
  return recommendedCoachReasons(coach);
});

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

/// Pinned journeys (local-only), wrapped in a real provider so mutations can
/// trigger a rebuild via `ref.invalidate` — unlike `localStoreProvider`
/// itself, which is a fixed value-override and never re-runs on invalidate.
final pinnedJourneysProvider = Provider<List<Map<String, dynamic>>>(
  (ref) => ref.watch(localStoreProvider).pinnedJourneys,
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

final weatherServiceProvider = Provider<WeatherService>((ref) => WeatherService());

/// Current conditions for the home greeting — the user's location when
/// available, else the network's home city, so the card always has
/// something to show. Null (never an error state) when offline or blocked;
/// weather is decorative context, not something worth interrupting for.
final weatherProvider = FutureProvider<Weather?>((ref) async {
  final locationResult = await ref.watch(locationServiceProvider).currentPosition();
  final (lat, lon) = switch (locationResult) {
    LocationFix(:final lat, :final lon) => (lat, lon),
    _ => (AppConfig.initialLat, AppConfig.initialLon),
  };
  return ref.watch(weatherServiceProvider).current(lat: lat, lon: lon);
});

final airQualityServiceProvider =
    Provider<AirQualityService>((ref) => AirQualityService());

/// Current air quality for the home air card — same location rule as
/// [weatherProvider] (device fix when available, else the network's home
/// city). Null (never an error) when offline or blocked; like weather, air
/// quality is ambient context, not something worth interrupting for. When it
/// is null the card renders nothing at all.
final airQualityProvider = FutureProvider<AirQuality?>((ref) async {
  final locationResult = await ref.watch(locationServiceProvider).currentPosition();
  final (lat, lon) = switch (locationResult) {
    LocationFix(:final lat, :final lon) => (lat, lon),
    _ => (AppConfig.initialLat, AppConfig.initialLon),
  };
  return ref.watch(airQualityServiceProvider).current(lat: lat, lon: lon);
});

/// Step-free / elevation summary for the curated station set, as a flat
/// {stop_id: elevated?} map (see [StationsRepository.facilitiesSummary]).
/// Empty offline or when DMRC hasn't published it. Static curated data, so it
/// stays out of Home's 30-second refresh loop.
final facilitiesSummaryProvider = FutureProvider<Map<String, bool?>>(
  (ref) => ref.watch(stationsRepositoryProvider).facilitiesSummary(),
);

/// The whole-percent share of the user's usual commute route that runs
/// underground, derived from the planned route's stations crossed with the
/// facilities elevation summary. Null when there's no commute route to
/// measure, or no station along it has a known elevation — so the air card
/// only ever quotes a figure it can actually back with data.
final commuteUndergroundShareProvider = FutureProvider<int?>((ref) async {
  final plan = await ref.watch(homeSuggestedPlanProvider.future);
  if (plan == null) return null;
  final facilities = await ref.watch(facilitiesSummaryProvider.future);
  if (facilities.isEmpty) return null;
  final stopIds = <String>[];
  for (final leg in plan.legs) {
    if (!leg.isRide) continue;
    for (final stop in leg.stations ?? [leg.board, leg.alight]) {
      stopIds.add(stop.stopId);
    }
  }
  return undergroundSharePercent(stopIds, facilities);
});

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
