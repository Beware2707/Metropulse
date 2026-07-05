import 'package:freezed_annotation/freezed_annotation.dart';

part 'eta.freezed.dart';
part 'eta.g.dart';

/// ETA to one station on a train's remaining run.
@freezed
class StationEta with _$StationEta {
  const factory StationEta({
    required String stopId,
    required String stopName,
    required int sequence,
    required double distanceRemainingM,
    required double etaSeconds,
    required DateTime etaTime,
  }) = _StationEta;

  factory StationEta.fromJson(Map<String, dynamic> json) =>
      _$StationEtaFromJson(json);
}

/// The full ETA fan-out for a vehicle.
@freezed
class VehicleEta with _$VehicleEta {
  const factory VehicleEta({
    required String vehicleId,
    required String tripId,
    required DateTime computedAt,
    required String confidence,
    StationEta? nextStation,
    double? delaySeconds,
    @Default(<StationEta>[]) List<StationEta> stations,
  }) = _VehicleEta;

  factory VehicleEta.fromJson(Map<String, dynamic> json) =>
      _$VehicleEtaFromJson(json);
}
