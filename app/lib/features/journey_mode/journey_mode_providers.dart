import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/journey_progress.dart';
import '../../domain/journey_timetable.dart';
import '../../domain/models/eta.dart';
import '../../domain/models/journey.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';

/// Ticks once a second so timetable-simulated progress updates live even
/// though nothing external pushes events for it (unlike the live-vehicle
/// path, which updates from the WebSocket stream).
final secondTickerProvider = StreamProvider<int>(
  (ref) => Stream<int>.periodic(const Duration(seconds: 1), (i) => i),
);

/// The plan-derived context persisted at journey start: everything needed to
/// recover Journey Mode after backgrounding or a full process restart.
class JourneyContext {
  const JourneyContext({
    required this.plan,
    required this.startedAt,
    required this.interchangeStopIds,
    this.recommendedCoach,
    this.routeLongName,
    this.routeColor,
    this.platformHint,
    this.crowding,
    this.coachReasons = const [],
    this.crowdSource,
  });

  final JourneyPlan? plan;
  final DateTime startedAt;
  final List<String> interchangeStopIds;
  final int? recommendedCoach;
  final String? routeLongName;
  final String? routeColor;
  final String? platformHint;

  /// 'low' | 'moderate' | 'high', mirroring the same coach-occupancy
  /// thresholds as the backend's commute_card.py — computed once at journey
  /// start from the coach recommendation already fetched then. Null when
  /// that call failed or returned no coach data, in which case the
  /// "Entering the Station" moment simply omits expected crowd rather than
  /// guessing at it.
  final String? crowding;

  /// Why this coach — the recommendation's own `reasons` list (e.g.
  /// "typically less crowded"), captured once at journey start.
  final List<String> coachReasons;

  /// 'observed' | 'prior' | 'model' — whether the crowd figures behind the
  /// coach recommendation are real live data or a fallback, so the app never
  /// silently presents a guess as a measurement.
  final String? crowdSource;
}

final journeyContextProvider = Provider.family<JourneyContext?, int>((ref, journeyId) {
  final raw = ref.watch(localStoreProvider).journeyContext(journeyId);
  if (raw == null) return null;
  final planJson = raw['plan'];
  return JourneyContext(
    plan: planJson is Map<String, dynamic> ? JourneyPlan.fromJson(planJson) : null,
    startedAt: DateTime.tryParse('${raw['started_at']}') ?? DateTime.now(),
    interchangeStopIds: [
      for (final id in (raw['interchange_stop_ids'] as List<dynamic>? ?? const [])) '$id',
    ],
    recommendedCoach: (raw['recommended_coach'] as num?)?.toInt(),
    routeLongName: raw['route_long_name'] as String?,
    routeColor: raw['route_color'] as String?,
    platformHint: raw['platform_hint'] as String?,
    crowding: raw['crowding'] as String?,
    coachReasons: [for (final r in (raw['coach_reasons'] as List<dynamic>? ?? const [])) '$r'],
    crowdSource: raw['crowd_source'] as String?,
  );
});

/// ETA for the tracked train, re-fetched only when its WS state changes (the
/// feed timestamp is part of the provider key — event-driven, no polling).
final journeyModeEtaProvider = FutureProvider.autoDispose
    .family<VehicleEta?, (String, String)>((ref, key) async {
  return ref.watch(trainsRepositoryProvider).eta(key.$1);
});

/// The unified progress snapshot: a live, fresh WS-tracked vehicle when one
/// is bound to the journey, otherwise the GTFS-timetable simulation. This is
/// the ONE thing Journey Mode's UI needs — see [JourneyProgressSnapshot].
final journeyProgressProvider =
    Provider.family<JourneyProgressSnapshot?, Journey>((ref, journey) {
  final context = ref.watch(journeyContextProvider(journey.id));
  final interchangeIds = context?.interchangeStopIds.toSet() ?? const <String>{};

  final train = journey.vehicleId == null
      ? null
      : ref.watch(liveTrainProvider(journey.vehicleId!));
  if (train != null && !train.isStale) {
    final eta = ref
        .watch(journeyModeEtaProvider(
          (journey.vehicleId!, train.vehicle.timestamp.toIso8601String()),
        ))
        .valueOrNull;
    final totalStations =
        context?.plan?.remainingStations.length ?? train.remainingStations.length;
    return fromLiveTrain(
      train: train,
      destinationStopId: journey.destinationStopId,
      interchangeStopIds: interchangeIds,
      totalStations: totalStations,
      eta: eta,
    );
  }

  final plan = context?.plan;
  if (plan == null) return null; // no live train and no plan snapshot to simulate from
  ref.watch(secondTickerProvider); // re-evaluate once a second
  final timetable = JourneyTimetable.fromPlan(plan, startedAt: context!.startedAt);
  return fromTimetable(timetable, DateTime.now(), interchangeStopIds: interchangeIds);
});

/// Creates a backend destination alert the first time a live vehicle is
/// bound to a journey, so the platform-native "approaching your stop"
/// notification (see the notifications sync controller) reinforces the
/// in-app banner. Deduplicated via a persisted flag so it survives both
/// re-watching this provider and a full app restart.
final destinationAlertCreationProvider = FutureProvider.family<void, (int, String, String)>(
  (ref, key) async {
    final (journeyId, vehicleId, destinationStopId) = key;
    final store = ref.read(localStoreProvider);
    final context = store.journeyContext(journeyId) ?? <String, dynamic>{};
    if (context['destination_alert_created'] == true) return;
    try {
      await ref.read(destinationAlertsRepositoryProvider).create(
            vehicleId: vehicleId,
            targetStopId: destinationStopId,
          );
    } on Exception {
      return; // best-effort: leave unflagged so a later attempt can retry
    }
    await store.saveJourneyContext(journeyId, {...context, 'destination_alert_created': true});
  },
);
