import 'dart:convert';

import 'package:dio/dio.dart';

import '../domain/models/commute_card.dart';
import '../domain/models/eta.dart';
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

/// Journey planning and journey-session lifecycle.
class JourneyRepository {
  JourneyRepository(this._api);

  final ApiClient _api;

  Future<JourneyPlan> plan(String origin, String destination) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/api/v1/journey/plan',
      queryParameters: {'origin': origin, 'destination': destination},
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

  Future<List<Journey>> history({int limit = 5}) async {
    final response = await _api.dio.get<Map<String, dynamic>>(
      '/api/v1/me/journeys',
      queryParameters: {'limit': limit},
    );
    final rows = response.data?['journeys'] as List<dynamic>? ?? const [];
    return rows
        .whereType<Map<String, dynamic>>()
        .map(Journey.fromJson)
        .toList(growable: false);
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

/// Favourite stations.
class FavouritesRepository {
  FavouritesRepository(this._api);

  final ApiClient _api;

  Future<List<Map<String, dynamic>>> list() async {
    final response = await _api.dio.get<List<dynamic>>(
      '/api/v1/me/favourites/stations',
    );
    return (response.data ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList();
  }

  Future<void> save(String stopId, {String? label, int position = 0}) =>
      _api.dio.put<Map<String, dynamic>>(
        '/api/v1/me/favourites/stations/$stopId',
        data: {'label': label, 'position': position},
      );

  Future<void> remove(String stopId) =>
      _api.dio.delete<void>('/api/v1/me/favourites/stations/$stopId');
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
