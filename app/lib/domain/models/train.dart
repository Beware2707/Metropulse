import 'package:freezed_annotation/freezed_annotation.dart';

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
  const factory Vehicle({
    required String vehicleId,
    required double latitude,
    required double longitude,
    required DateTime timestamp,
    String? tripId,
    String? routeId,
    double? bearing,
    double? speedMps,
  }) = _Vehicle;

  factory Vehicle.fromJson(Map<String, dynamic> json) => _$VehicleFromJson(json);
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

  String get lineLabel => routeLongName ?? routeShortName ?? 'Unknown line';
}
