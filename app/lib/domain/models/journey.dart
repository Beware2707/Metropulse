import 'package:freezed_annotation/freezed_annotation.dart';

part 'journey.freezed.dart';
part 'journey.g.dart';

/// A stop within a journey plan.
@freezed
class JourneyStop with _$JourneyStop {
  const factory JourneyStop({required String stopId, required String name}) =
      _JourneyStop;

  factory JourneyStop.fromJson(Map<String, dynamic> json) =>
      _$JourneyStopFromJson(json);
}

/// One ride or walk leg of a plan.
@freezed
class JourneyLeg with _$JourneyLeg {
  const JourneyLeg._();

  const factory JourneyLeg({
    required String kind,
    required JourneyStop board,
    required JourneyStop alight,
    required double seconds,
    String? routeId,
    String? routeLongName,
    String? routeColor,
    int? directionId,
    String? platformHint,
    double? waitSeconds,
    List<JourneyStop>? stations,
    double? distanceM,
  }) = _JourneyLeg;

  factory JourneyLeg.fromJson(Map<String, dynamic> json) =>
      _$JourneyLegFromJson(json);

  bool get isRide => kind == 'ride';
}

/// A complete origin-to-destination plan.
@freezed
class JourneyPlan with _$JourneyPlan {
  const factory JourneyPlan({
    required JourneyStop origin,
    required JourneyStop destination,
    required DateTime departureAt,
    required DateTime expectedArrivalAt,
    required double expectedTravelSeconds,
    required int interchangeCount,
    required List<String> interchangeStopIds,
    required double walkingDistanceM,
    required List<JourneyStop> remainingStations,
    required List<JourneyLeg> legs,
  }) = _JourneyPlan;

  factory JourneyPlan.fromJson(Map<String, dynamic> json) =>
      _$JourneyPlanFromJson(json);
}

/// A tracked journey (the server-side session).
@freezed
class Journey with _$Journey {
  const factory Journey({
    required int id,
    required String originStopId,
    required String destinationStopId,
    required String status,
    required DateTime startedAt,
    String? routeId,
    String? vehicleId,
    DateTime? endedAt,
  }) = _Journey;

  factory Journey.fromJson(Map<String, dynamic> json) => _$JourneyFromJson(json);
}
