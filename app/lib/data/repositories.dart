import 'dart:convert';

import 'package:dio/dio.dart';

import '../domain/models/commute_card.dart';
import '../domain/models/eta.dart';
import '../domain/models/intelligence.dart';
import '../domain/models/journey.dart';
import '../domain/models/station.dart';
import '../domain/models/train.dart';
import 'api_client.dart';
import 'local_store.dart';

/// Stations with offline-first semantics: the Hive-cached bundle is served
/// immediately; a background refresh uses the manifest version (cheap) and
/// only downloads the bundle when it changed.
class StationsRepository {
  StationsRepository(this._api, this._store);

  final ApiClient _api;
  final LocalStore _store;

  OfflineBundle? get cached => _store.cachedBundle;

  Future<OfflineBundle?> refreshIfStale() async {
    try {
      final manifest = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/offline/manifest',
      );
      final version = manifest.data?['version'] as String?;
      if (version == null) return cached;
      if (version == _store.cachedBundleVersion && cached != null) {
        return cached;
      }
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/offline/bundle',
      );
      final data = response.data;
      if (data == null) return cached;
      final bundle = OfflineBundle.fromJson(data);
      await _store.saveBundle(bundle, jsonEncode(data));
      return bundle;
    } on DioException {
      return cached; // offline: the cache is the product, not a fallback
    }
  }

  Future<Map<String, dynamic>?> lastTrain(String stopId) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/stations/$stopId/last-train',
      );
      return response.data;
    } on DioException {
      return null;
    }
  }

  Future<List<Map<String, dynamic>>> exits(String stopId) async {
    try {
      final response = await _api.dio.get<List<dynamic>>(
        '/api/v1/stations/$stopId/exits',
      );
      return (response.data ?? const [])
          .whereType<Map<String, dynamic>>()
          .toList();
    } on DioException {
      return const [];
    }
  }
}

/// Live-train reads (the WS stream is primary; these back detail screens).
class TrainsRepository {
  TrainsRepository(this._api);

  final ApiClient _api;

  Future<Train?> train(String vehicleId) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/trains/$vehicleId',
      );
      final data = response.data;
      return data == null ? null : Train.fromJson(data);
    } on DioException {
      return null;
    }
  }

  Future<VehicleEta?> eta(String vehicleId) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/eta/$vehicleId',
      );
      final data = response.data;
      return data == null ? null : VehicleEta.fromJson(data);
    } on DioException {
      return null;
    }
  }
}

/// Route preference for [JourneyRepository.plan] — mirrors the backend's
/// `RoutePreference` enum. Wheelchair-friendly routing isn't offered here
/// because the loaded GTFS dataset carries no accessibility data yet; the
/// planner screen surfaces that honestly rather than pretending to route
/// around it.
enum RoutePreference { fastest, fewerTransfers, lessWalking }

extension on RoutePreference {
  String get wireValue => switch (this) {
        RoutePreference.fastest => 'fastest',
        RoutePreference.fewerTransfers => 'fewer_transfers',
        RoutePreference.lessWalking => 'less_walking',
      };
}

/// Journey planning and journey-session lifecycle.
class JourneyRepository {
  JourneyRepository(this._api, this._store);

  final ApiClient _api;
  final LocalStore _store;

  Future<JourneyPlan> plan(
    String origin,
    String destination, {
    RoutePreference preference = RoutePreference.fastest,
  }) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/api/v1/journey/plan',
      queryParameters: {
        'origin': origin,
        'destination': destination,
        'preference': preference.wireValue,
      },
    );
    return JourneyPlan.fromJson(response.data!);
  }

  Future<Journey> start({
    required String origin,
    required String destination,
    String? vehicleId,
    String? routeId,
    List<String> interchangeStopIds = const [],
  }) async {
    final response = await _api.dio.post<Map<String, dynamic>>(
      '/api/v1/me/journeys',
      data: {
        'origin_stop_id': origin,
        'destination_stop_id': destination,
        'vehicle_id': vehicleId,
        'route_id': routeId,
        'interchange_stop_ids': interchangeStopIds,
      },
    );
    return Journey.fromJson(response.data!);
  }

  Future<Journey?> current() async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/me/journeys/current',
      );
      return Journey.fromJson(response.data!);
    } on DioException catch (error) {
      if (error.response?.statusCode == 404) return null;
      rethrow;
    }
  }

  /// Journey history, offline-first: a successful fetch refreshes the local
  /// cache; a failed one (no connectivity) falls back to that cache so the
  /// commuter's history remains visible offline, per the offline-support
  /// requirement — this list is REST data, not part of the offline bundle.
  Future<List<Journey>> history({int limit = 5}) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/me/journeys',
        queryParameters: {'limit': limit},
      );
      final rows = (response.data?['journeys'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .toList(growable: false);
      await _store.saveJourneyHistoryCache(rows);
      return rows.map(Journey.fromJson).toList(growable: false);
    } on DioException {
      final cached = _store.cachedJourneyHistory;
      if (cached == null) rethrow;
      return cached.map(Journey.fromJson).toList(growable: false);
    }
  }

  Future<Map<String, dynamic>?> coachRecommendation({
    required String origin,
    required String destination,
    String? routeId,
    int? directionId,
  }) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/recommendations/coach',
        queryParameters: {
          'origin': origin,
          'destination': destination,
          if (routeId != null) 'route_id': routeId,
          if (directionId != null) 'direction_id': directionId,
        },
      );
      return response.data;
    } on DioException {
      return null;
    }
  }

  Future<void> end(int journeyId, {required bool completed}) async {
    final action = completed ? 'complete' : 'abandon';
    await _api.dio.post<Map<String, dynamic>>(
      '/api/v1/me/journeys/$journeyId/$action',
    );
  }

  Future<Map<String, dynamic>?> bestExit(
    String stopId, {
    String? routeId,
    int? directionId,
  }) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/recommendations/exit',
        queryParameters: {
          'station': stopId,
          if (routeId != null) 'route_id': routeId,
          if (directionId != null) 'direction_id': directionId,
        },
      );
      final exits = response.data?['exits'] as List<dynamic>?;
      return exits?.whereType<Map<String, dynamic>>().firstOrNull;
    } on DioException {
      return null; // exits are curated data; absence is normal
    }
  }
}

/// Active service alerts (disruptions).
class AlertsRepository {
  AlertsRepository(this._api);

  final ApiClient _api;

  Future<List<Map<String, dynamic>>> active() async {
    final response = await _api.dio.get<Map<String, dynamic>>('/api/v1/alerts');
    final rows = response.data?['alerts'] as List<dynamic>? ?? const [];
    return rows.whereType<Map<String, dynamic>>().toList(growable: false);
  }
}

/// Favourite stations, with an offline-fallback cache (see [JourneyRepository.history]).
class FavouritesRepository {
  FavouritesRepository(this._api, this._store);

  final ApiClient _api;
  final LocalStore _store;

  Future<List<Map<String, dynamic>>> list() async {
    try {
      final response = await _api.dio.get<List<dynamic>>(
        '/api/v1/me/favourites/stations',
      );
      final rows = (response.data ?? const [])
          .whereType<Map<String, dynamic>>()
          .toList(growable: false);
      await _store.saveFavouriteStationsCache(rows);
      return rows;
    } on DioException {
      final cached = _store.cachedFavouriteStations;
      if (cached == null) rethrow;
      return cached;
    }
  }

  Future<void> save(String stopId, {String? label, int position = 0}) =>
      _api.dio.put<Map<String, dynamic>>(
        '/api/v1/me/favourites/stations/$stopId',
        data: {'label': label, 'position': position},
      );

  Future<void> remove(String stopId) =>
      _api.dio.delete<void>('/api/v1/me/favourites/stations/$stopId');
}

/// The user's notification inbox — these are the surfaced form of every
/// backend-scheduled alert (destination, interchange, last-train,
/// leave-home, missed-stop, delay, service alert).
class NotificationsRepository {
  NotificationsRepository(this._api);

  final ApiClient _api;

  Future<List<Map<String, dynamic>>> list({int limit = 50}) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/api/v1/me/notifications',
      queryParameters: {'limit': limit},
    );
    final rows = response.data?['notifications'] as List<dynamic>? ?? const [];
    return rows.whereType<Map<String, dynamic>>().toList(growable: false);
  }

  Future<void> markRead(int notificationId) => _api.dio
      .post<void>('/api/v1/me/notifications/$notificationId/read');
}

/// Destination alerts: "tell me when my train nears my stop" — created
/// automatically by Journey Mode once a live vehicle is bound to a journey.
class DestinationAlertsRepository {
  DestinationAlertsRepository(this._api);

  final ApiClient _api;

  Future<void> create({
    required String vehicleId,
    required String targetStopId,
    int thresholdSeconds = 120,
  }) =>
      _api.dio.post<Map<String, dynamic>>(
        '/api/v1/me/alerts/destination',
        data: {
          'vehicle_id': vehicleId,
          'target_stop_id': targetStopId,
          'threshold_seconds': thresholdSeconds,
        },
      );
}

/// Last-train and leave-home reminders, scheduled entirely by the backend —
/// this only submits the request.
class RemindersRepository {
  RemindersRepository(this._api);

  final ApiClient _api;

  Future<void> createLastTrain({
    required String stopId,
    String? routeId,
    int? directionId,
    int leadMinutes = 30,
  }) =>
      _api.dio.post<Map<String, dynamic>>(
        '/api/v1/me/reminders/last-train',
        data: {
          'stop_id': stopId,
          'route_id': routeId,
          'direction_id': directionId,
          'lead_minutes': leadMinutes,
        },
      );

  Future<void> createLeaveHome({
    required String stopId,
    required DateTime trainDepartureAt,
    required int walkingMinutes,
    int bufferMinutes = 10,
  }) =>
      _api.dio.post<Map<String, dynamic>>(
        '/api/v1/me/reminders/leave-home',
        data: {
          'stop_id': stopId,
          'train_departure_at': trainDepartureAt.toUtc().toIso8601String(),
          'walking_minutes': walkingMinutes,
          'buffer_minutes': bufferMinutes,
        },
      );
}

/// The home-screen commute card.
class CommuteRepository {
  CommuteRepository(this._api);

  final ApiClient _api;

  /// Returns null when the commute isn't configured yet (backend 409).
  Future<CommuteCard?> card() async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/me/commute-card',
      );
      return CommuteCard.fromJson(response.data!);
    } on DioException catch (error) {
      if (error.response?.statusCode == 409) return null;
      rethrow;
    }
  }
}

/// Metro Intelligence: commute prediction, delay estimation, and smart
/// route/coach/exit recommendations — all derived from GTFS schedules and
/// the user's own journey history, never a black-box model.
class IntelligenceRepository {
  IntelligenceRepository(this._api);

  final ApiClient _api;

  /// The commute this user is most likely making right now. Returns null
  /// when there isn't enough journey history yet (backend 404) — not an
  /// error, just "nothing learned yet".
  Future<CommutePrediction?> commutePrediction() async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/intelligence/me/commute-prediction',
      );
      return CommutePrediction.fromJson(response.data!);
    } on DioException catch (error) {
      if (error.response?.statusCode == 404) return null;
      rethrow;
    }
  }

  /// Typical delay for a route around the current time of day.
  Future<DelayEstimate> delayEstimate({required String routeId, int? directionId}) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/api/v1/intelligence/delay-estimate',
      queryParameters: {
        'route_id': routeId,
        if (directionId != null) 'direction_id': directionId,
      },
    );
    return DelayEstimate.fromJson(response.data!);
  }

  /// Best route, departure time, coach and exit for a trip. Returns null
  /// when nothing connects the two stations (backend 404).
  Future<SmartRecommendation?> recommendations({
    required String origin,
    required String destination,
  }) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/intelligence/recommendations',
        queryParameters: {'origin': origin, 'destination': destination},
      );
      return SmartRecommendation.fromJson(response.data!);
    } on DioException catch (error) {
      if (error.response?.statusCode == 404) return null;
      rethrow;
    }
  }

  /// Places inferred from this user's own journey history (Home, and a
  /// regular weekday destination) — suggestions to offer, e.g. as
  /// pre-filled Favourites labels. Empty when nothing's been learned yet.
  Future<List<InferredPlace>> inferredPlaces() async {
    final response = await _api.dio.get<List<dynamic>>(
      '/api/v1/intelligence/me/inferred-places',
    );
    return (response.data ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(InferredPlace.fromJson)
        .toList(growable: false);
  }
}
