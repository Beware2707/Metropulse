import 'package:freezed_annotation/freezed_annotation.dart';

import '../../core/formatters.dart';

part 'train.freezed.dart';
part 'train.g.dart';

/// A station reference inside a train state.
@freezed
class StationRef with _$StationRef {
  const factory StationRef({
    required String stopId,
    required String name,
    required int sequence,
  }) = _StationRef;

  factory StationRef.fromJson(Map<String, dynamic> json) =>
      _$StationRefFromJson(json);
}

/// The raw vehicle position within a train state.
@freezed
class Vehicle with _$Vehicle {
  const Vehicle._();

  const factory Vehicle({
    required String vehicleId,
    required double latitude,
    required double longitude,
    required DateTime timestamp,
    String? tripId,
    String? routeId,
    double? bearing,
    double? speedMps,
    // "realtime_gps" (an actual feed) or "schedule_estimate" (interpolated
    // from the timetable when no licensed realtime feed is configured) --
    // see backend domain.entities.VehiclePosition.
    //
    // Defaults to schedule_estimate so the honesty check FAILS CLOSED. The
    // backend declares `source` required, so a payload without it means
    // something is wrong (an old cache, a schema drift, an explicit null) --
    // exactly when we least deserve the benefit of the doubt. Defaulting to
    // realtime_gps made `isEstimated` false and painted a green LIVE badge
    // over interpolated data, which is the one lie this app must never tell.
    // Understating (SCHEDULE over real GPS) is recoverable; overclaiming is
    // not. And today it is simply true: there is no DMRC realtime feed.
    @Default('schedule_estimate') String source,
  }) = _Vehicle;

  factory Vehicle.fromJson(Map<String, dynamic> json) => _$VehicleFromJson(json);

  /// Whether this position is interpolated rather than real GPS.
  ///
  /// Deliberately phrased as "anything that isn't explicitly realtime_gps",
  /// not "== schedule_estimate". Only an affirmative realtime_gps earns a
  /// green LIVE badge; an unknown or future source value must not. Written
  /// the other way round, a new backend tag (or a typo) would silently be
  /// treated as live — the same fail-open trap as the old default.
  bool get isEstimated => source != 'realtime_gps';
}

/// A fully resolved live train, exactly as broadcast by the backend.
@freezed
class Train with _$Train {
  const Train._();

  const factory Train({
    required Vehicle vehicle,
    required bool resolved,
    required bool isStale,
    String? routeId,
    String? routeShortName,
    String? routeLongName,
    String? routeColor,
    String? headsign,
    int? directionId,
    StationRef? currentStation,
    StationRef? nextStation,
    StationRef? destination,
    @Default(false) bool atStation,
    @Default(<StationRef>[]) List<StationRef> remainingStations,
  }) = _Train;

  factory Train.fromJson(Map<String, dynamic> json) => _$TrainFromJson(json);

  String get id => vehicle.vehicleId;

  String get lineLabel => cleanLineName(routeLongName ?? routeShortName);

  bool get isEstimated => vehicle.isEstimated;
}
