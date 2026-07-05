import 'package:freezed_annotation/freezed_annotation.dart';

part 'station.freezed.dart';
part 'station.g.dart';

/// A metro station from the offline bundle.
@freezed
class Station with _$Station {
  const factory Station({
    required String stopId,
    required String name,
    required double lat,
    required double lon,
  }) = _Station;

  factory Station.fromJson(Map<String, dynamic> json) => _$StationFromJson(json);
}

/// A metro line from the offline bundle.
@freezed
class RouteLine with _$RouteLine {
  const factory RouteLine({
    required String routeId,
    String? shortName,
    String? longName,
    String? color,
  }) = _RouteLine;

  factory RouteLine.fromJson(Map<String, dynamic> json) =>
      _$RouteLineFromJson(json);
}

/// The offline dataset: stations, lines and per-direction station sequences.
@freezed
class OfflineBundle with _$OfflineBundle {
  const factory OfflineBundle({
    required String version,
    required List<Station> stations,
    required List<RouteLine> routes,
    // route_id -> direction ("0"/"1") -> ordered stop ids
    required Map<String, Map<String, List<String>>> routeStations,
  }) = _OfflineBundle;

  factory OfflineBundle.fromJson(Map<String, dynamic> json) =>
      _$OfflineBundleFromJson(json);
}
