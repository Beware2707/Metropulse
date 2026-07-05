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

/// A curated station exit, including searchable landmark names.
@freezed
class StationExitInfo with _$StationExitInfo {
  const factory StationExitInfo({
    required int id,
    required String name,
    String? description,
    @Default(<String>[]) List<String> landmarks,
  }) = _StationExitInfo;

  factory StationExitInfo.fromJson(Map<String, dynamic> json) =>
      _$StationExitInfoFromJson(json);
}

/// The offline dataset: stations, lines, per-direction station sequences and
/// curated exits/landmarks — everything Search needs works fully offline.
@freezed
class OfflineBundle with _$OfflineBundle {
  const factory OfflineBundle({
    required String version,
    required List<Station> stations,
    required List<RouteLine> routes,
    // route_id -> direction ("0"/"1") -> ordered stop ids
    required Map<String, Map<String, List<String>>> routeStations,
    // stop_id -> curated exits; absent for stations with none, and absent
    // entirely on bundles cached before this field existed.
    @Default(<String, List<StationExitInfo>>{})
    Map<String, List<StationExitInfo>> exits,
  }) = _OfflineBundle;

  factory OfflineBundle.fromJson(Map<String, dynamic> json) =>
      _$OfflineBundleFromJson(json);
}
