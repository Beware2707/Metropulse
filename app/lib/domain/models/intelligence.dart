import 'package:freezed_annotation/freezed_annotation.dart';

part 'intelligence.freezed.dart';
part 'intelligence.g.dart';

/// The commute this user is most likely making right now, learned from
/// their own journey history — not a generic "next scheduled train" lookup.
/// `confidence` (0..1) and `sampleSize` are always present so the UI can be
/// honest about how sure a prediction really is.
@freezed
class CommutePrediction with _$CommutePrediction {
  const factory CommutePrediction({
    required String originStopId,
    required String originName,
    required String destinationStopId,
    required String destinationName,
    String? routeId,
    String? routeLongName,
    required DateTime predictedDepartureAt,
    double? predictedDurationSeconds,
    int? recommendedCoach,
    String? recommendedExitName,
    required double confidence,
    required int sampleSize,
    required String basis,
  }) = _CommutePrediction;

  factory CommutePrediction.fromJson(Map<String, dynamic> json) =>
      _$CommutePredictionFromJson(json);
}

/// Typical delay for a route around an hour of day, from historical
/// completed-journey durations vs. GTFS-scheduled duration.
@freezed
class DelayEstimate with _$DelayEstimate {
  const factory DelayEstimate({
    required String routeId,
    int? directionId,
    required int hourOfDay,
    required double expectedDelaySeconds,
    required double confidence,
    required int sampleSize,
  }) = _DelayEstimate;

  factory DelayEstimate.fromJson(Map<String, dynamic> json) =>
      _$DelayEstimateFromJson(json);
}

/// One scored route option inside a smart-recommendation bundle.
@freezed
class RouteRecommendation with _$RouteRecommendation {
  const factory RouteRecommendation({
    required String preference,
    required double travelSeconds,
    required int interchangeCount,
    required double walkingDistanceM,
    required double delayAdjustedSeconds,
    required List<String> reasons,
  }) = _RouteRecommendation;

  factory RouteRecommendation.fromJson(Map<String, dynamic> json) =>
      _$RouteRecommendationFromJson(json);
}

/// The synthesised "what should I do" bundle for an origin/destination pair.
@freezed
class SmartRecommendation with _$SmartRecommendation {
  const factory SmartRecommendation({
    required String originStopId,
    required String destinationStopId,
    DateTime? bestDepartureAt,
    RouteRecommendation? bestRoute,
    required List<RouteRecommendation> alternatives,
    int? recommendedCoach,
    String? recommendedExitName,
    required bool leastCrowdedAvailable,
  }) = _SmartRecommendation;

  factory SmartRecommendation.fromJson(Map<String, dynamic> json) =>
      _$SmartRecommendationFromJson(json);
}

/// A place role inferred from journey history — a suggestion to offer the
/// user (e.g. pre-filling a Favourites label), never written on their
/// behalf. `role` is `"home"` or `"weekday_anchor"`: movement data alone
/// can't tell "Office" from "College", so the app just calls it a regular
/// weekday destination and lets the user name it.
@freezed
class InferredPlace with _$InferredPlace {
  const factory InferredPlace({
    required String stopId,
    required String stopName,
    required String role,
    required double confidence,
    required int sampleSize,
    required String rationale,
  }) = _InferredPlace;

  factory InferredPlace.fromJson(Map<String, dynamic> json) =>
      _$InferredPlaceFromJson(json);
}
