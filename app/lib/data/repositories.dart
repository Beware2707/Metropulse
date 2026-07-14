import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show defaultTargetPlatform;

import '../core/config.dart';
import '../domain/models/commute_card.dart';
import '../domain/models/eta.dart';
import '../domain/models/intelligence.dart';
import '../domain/models/journey.dart';
import '../domain/models/replay.dart';
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

  Future<Map<String, dynamic>?> facilities(String stopId) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/stations/$stopId/facilities',
      );
      return response.data;
    } on DioException {
      return null;
    }
  }

  Future<List<Map<String, dynamic>>> lastMileRoutes(String stopId) async {
    try {
      final response = await _api.dio.get<List<dynamic>>(
        '/api/v1/stations/$stopId/last-mile',
      );
      return (response.data ?? const [])
          .whereType<Map<String, dynamic>>()
          .toList();
    } on DioException {
      return const [];
    }
  }

  /// Step-free access summary for the curated station set: a flat
  /// {stop_id: elevated} map where `true` means the platform is elevated (so
  /// stairs/lift, not concourse-level), `false` means at/below grade, and
  /// `null` means DMRC hasn't published it — kept as a nullable so callers
  /// can be honest about "unknown" rather than guessing. Flattens the
  /// backend's {stop_id: {elevated: x}} shape. Empty on 404 or offline.
  Future<Map<String, bool?>> facilitiesSummary() async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/stations/facilities/summary',
      );
      final facilities =
          response.data?['facilities'] as Map<String, dynamic>? ?? const {};
      return {
        for (final entry in facilities.entries)
          entry.key:
              (entry.value as Map<String, dynamic>?)?['elevated'] as bool?,
      };
    } on DioException {
      return const {};
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

  /// The latest departure from [origin] today that still catches every
  /// leg's final feasible trip to [destination] — straight from the
  /// published timetable, no live data. Typed-map passthrough of
  /// GET /api/v1/journeys/latest-departure. Null on 404 (unknown stop or no
  /// same-service-day path) or offline — callers simply don't show the row.
  Future<Map<String, dynamic>?> latestDeparture(
    String origin,
    String destination,
  ) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/journeys/latest-departure',
        queryParameters: {'origin': origin, 'destination': destination},
      );
      return response.data;
    } on DioException {
      return null;
    }
  }

  /// Park-and-ride candidates: stations with DMRC-published parking
  /// capacity (static capacity, never live availability), ranked by
  /// straight-line distance from ([lat], [lon]) plus metro time to
  /// [destination]. Typed-map passthrough of GET /api/v1/park-and-ride;
  /// empty on 404 or offline.
  Future<List<Map<String, dynamic>>> parkAndRide({
    required String destination,
    required double lat,
    required double lon,
  }) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/park-and-ride',
        queryParameters: {'destination': destination, 'lat': lat, 'lon': lon},
      );
      return (response.data?['candidates'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .toList(growable: false);
    } on DioException {
      return const [];
    }
  }

  /// How far every station is from [origin], in whole minutes by the
  /// published timetable (origin itself maps to 0) — the isochrone/reach
  /// data. Typed passthrough of GET /api/v1/journeys/reach, flattened to a
  /// {stop_id: minutes} map. Empty on 404 (unknown origin) or offline.
  Future<Map<String, int>> reach(String origin, {DateTime? at}) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/journeys/reach',
        queryParameters: {
          'origin': origin,
          if (at != null) 'at': at.toUtc().toIso8601String(),
        },
      );
      final reach = response.data?['reach'] as Map<String, dynamic>? ?? const {};
      return {
        for (final entry in reach.entries)
          if (entry.value is num) entry.key: (entry.value as num).toInt(),
      };
    } on DioException {
      return const {};
    }
  }

  /// Fair meeting points for two people starting at stops [a] and [b]:
  /// stations ranked fairness-first by the backend (smallest worst-case
  /// travel time, then smallest combined time), top 10. Each candidate
  /// carries stop_id, name, minutes_a, minutes_b, max_minutes and
  /// total_minutes. Typed-map passthrough of GET /api/v1/journeys/meet;
  /// empty on 404 (unknown stop) or offline.
  Future<List<Map<String, dynamic>>> meet(String a, String b) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/journeys/meet',
        queryParameters: {'a': a, 'b': b},
      );
      return (response.data?['candidates'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .toList(growable: false);
    } on DioException {
      return const [];
    }
  }

  Future<void> end(int journeyId, {required bool completed}) async {
    final action = completed ? 'complete' : 'abandon';
    await _api.dio.post<Map<String, dynamic>>(
      '/api/v1/me/journeys/$journeyId/$action',
    );
  }

  /// SHARE-MY-LIVE-JOURNEY: creates (or returns) a public share for the
  /// caller's OWN active journey. Returns {token, share_url, expires_at} on
  /// success; null on 404 (the journey isn't the caller's or isn't active) or
  /// offline — the UI then simply says it couldn't start sharing rather than
  /// pretending a link exists. The token is the only secret: the public read
  /// exposes journey facts, never the user's identity.
  Future<Map<String, dynamic>?> shareJourney(int journeyId) async {
    try {
      final response = await _api.dio.post<Map<String, dynamic>>(
        '/api/v1/me/journeys/$journeyId/share',
      );
      return response.data;
    } on DioException {
      return null;
    }
  }

  /// Records the sharer's own latest device GPS position for an active share.
  /// Best-effort by design: a 410 (share ended/expired) or a dropped
  /// connection is swallowed like the other lifecycle calls — the caller's
  /// polling loop stops on its own once sharing is torn down, so a lost tick
  /// is never worth surfacing.
  Future<void> postSharePosition(int journeyId, double lat, double lon) async {
    try {
      await _api.dio.post<Map<String, dynamic>>(
        '/api/v1/me/journeys/$journeyId/position',
        data: {'lat': lat, 'lon': lon},
      );
    } on DioException {
      // best-effort; the next tick retries and Stop tears the loop down
    }
  }

  /// Stops sharing immediately (the backend marks the public link expired).
  /// Swallows transport errors like [end] — stopping is the safe direction, so
  /// a failure here still tears the local sharing UI down.
  Future<void> stopSharing(int journeyId) async {
    try {
      await _api.dio.delete<Map<String, dynamic>>(
        '/api/v1/me/journeys/$journeyId/share',
      );
    } on DioException {
      // best-effort
    }
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

  /// Recent RIDER-sourced disruption reports — community-sourced and
  /// unverified, deliberately kept distinct from the authoritative operator
  /// alerts in [active]. Newest first, deduped/counted by (stop_id, category)
  /// within [sinceMinutes]. Each row: {id, stop_id, route_id, message,
  /// category, reported_at, count}. Empty on error or offline (swallowed like
  /// the other typed-map passthroughs), so the board just shows no commuter
  /// reports rather than an error.
  Future<List<Map<String, dynamic>>> riderReports({int sinceMinutes = 120}) async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/alerts/reports',
        queryParameters: {'since_minutes': sinceMinutes},
      );
      final rows = response.data?['reports'] as List<dynamic>? ?? const [];
      return rows.whereType<Map<String, dynamic>>().toList(growable: false);
    } on DioException {
      return const [];
    }
  }

  /// Submits a rider-sourced report (the backend stamps source='rider',
  /// unverified). Returns true when accepted (202), false on a validation
  /// error or offline — so the UI can honestly tell the commuter it didn't go
  /// through rather than silently dropping it.
  Future<bool> postRiderReport({
    String? stopId,
    String? routeId,
    required String message,
    String? category,
  }) async {
    try {
      await _api.dio.post<Map<String, dynamic>>(
        '/api/v1/alerts/reports',
        data: {
          if (stopId != null) 'stop_id': stopId,
          if (routeId != null) 'route_id': routeId,
          'message': message,
          if (category != null) 'category': category,
        },
      );
      return true;
    } on DioException {
      return false;
    }
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

/// Commute Replay: what a completed trip (or a month of them) actually cost
/// and saved — Spotify-Wrapped-style, but for the metro.
class ReplayRepository {
  ReplayRepository(this._api);

  final ApiClient _api;

  /// The most recently completed trip, replayed. Null when the user hasn't
  /// completed a journey yet (not an error).
  Future<TripReplay?> latestTrip() async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>('/api/v1/me/replay/latest-trip');
      return TripReplay.fromJson(response.data!);
    } on DioException catch (error) {
      if (error.response?.statusCode == 404) return null;
      rethrow;
    }
  }

  /// A rolling 30-day summary of the user's completed trips.
  Future<MonthlyReplay> monthly() async {
    final response = await _api.dio.get<Map<String, dynamic>>('/api/v1/me/replay/monthly');
    return MonthlyReplay.fromJson(response.data!);
  }

  /// A rolling 30-day fare estimate: how many trips the user took, roughly
  /// what they spent, and what a smart card (and off-peak riding) would have
  /// saved — every figure a documented estimate, not a billing statement.
  /// Typed-map passthrough of the authenticated GET /api/v1/me/fare-advisor
  /// (the bearer token is attached by [ApiClient]). Null on 401 (not
  /// registered) or offline; the backend returns zeros with a note when the
  /// user has no trip history yet.
  Future<Map<String, dynamic>?> fareAdvisor() async {
    try {
      final response = await _api.dio.get<Map<String, dynamic>>(
        '/api/v1/me/fare-advisor',
      );
      return response.data;
    } on DioException {
      return null;
    }
  }
}

/// In-app feedback (Sprint 4: beta launch) -- a message plus real, honest
/// context (app version, platform) rather than an anonymous string alone.
class FeedbackRepository {
  FeedbackRepository(this._api);

  final ApiClient _api;

  Future<void> submit({required String message, String? category}) => _api.dio.post<void>(
        '/api/v1/feedback',
        data: {
          'message': message,
          'category': category,
          'app_version': AppConfig.appVersion,
          'platform': defaultTargetPlatform.name,
        },
      );
}
