import 'dart:math' as math;
import 'dart:ui' show Offset, Size;

import 'models/station.dart';

/// The geographic extent of a set of stations — the raw min/max lat/lon the
/// schematic diagram is fit into.
class GeoBounds {
  const GeoBounds({
    required this.minLat,
    required this.maxLat,
    required this.minLon,
    required this.maxLon,
  });

  final double minLat;
  final double maxLat;
  final double minLon;
  final double maxLon;

  /// Bounds enclosing [stations], or null when the iterable is empty (nothing
  /// to project). Stations with identical coordinates collapse to a
  /// zero-span axis, which the projection centres rather than divides by.
  static GeoBounds? fromStations(Iterable<Station> stations) {
    double? minLat, maxLat, minLon, maxLon;
    for (final station in stations) {
      minLat = minLat == null ? station.lat : math.min(minLat, station.lat);
      maxLat = maxLat == null ? station.lat : math.max(maxLat, station.lat);
      minLon = minLon == null ? station.lon : math.min(minLon, station.lon);
      maxLon = maxLon == null ? station.lon : math.max(maxLon, station.lon);
    }
    if (minLat == null || maxLat == null || minLon == null || maxLon == null) {
      return null;
    }
    return GeoBounds(minLat: minLat, maxLat: maxLat, minLon: minLon, maxLon: maxLon);
  }
}

/// An honest equirectangular projection from real lat/lon into canvas pixels.
///
/// City-scale metro geography is small enough that an equirectangular
/// projection (longitude compressed by cos(latitude), so a degree of
/// longitude and a degree of latitude cover the same on-screen distance) keeps
/// the network's true shape — this is a *schematic* of real geometry, not an
/// invented layout. The projection fits [bounds] into [size] with uniform
/// scale on both axes and [padding] on every side, and centres a zero-span or
/// letterboxed diagram rather than stretching it.
class SchematicProjection {
  SchematicProjection({
    required this.bounds,
    required this.size,
    this.padding = 32,
  }) {
    final centerLatRad = ((bounds.minLat + bounds.maxLat) / 2) * math.pi / 180.0;
    _lonFactor = math.cos(centerLatRad).abs().clamp(1e-6, 1.0);

    final geoWidth = (bounds.maxLon - bounds.minLon).abs() * _lonFactor;
    final geoHeight = (bounds.maxLat - bounds.minLat).abs();

    final availWidth = math.max(size.width - 2 * padding, 1.0);
    final availHeight = math.max(size.height - 2 * padding, 1.0);

    final scaleX = geoWidth > 0 ? availWidth / geoWidth : double.infinity;
    final scaleY = geoHeight > 0 ? availHeight / geoHeight : double.infinity;
    var scale = math.min(scaleX, scaleY);
    if (!scale.isFinite || scale <= 0) scale = 1.0;
    _scale = scale;

    final contentWidth = geoWidth * scale;
    final contentHeight = geoHeight * scale;
    _offsetX = padding + (availWidth - contentWidth) / 2;
    _offsetY = padding + (availHeight - contentHeight) / 2;
  }

  final GeoBounds bounds;
  final Size size;
  final double padding;

  late final double _lonFactor;
  late final double _scale;
  late final double _offsetX;
  late final double _offsetY;

  /// Projects a real coordinate into canvas space. Latitude is inverted
  /// because canvas y grows downward while latitude grows northward, so the
  /// northernmost station sits at the top of the diagram.
  Offset project(double lat, double lon) {
    final x = _offsetX + (lon - bounds.minLon) * _lonFactor * _scale;
    final y = _offsetY + (bounds.maxLat - lat) * _scale;
    return Offset(x, y);
  }

  /// Projects a [Station] into canvas space.
  Offset projectStation(Station station) => project(station.lat, station.lon);
}

/// The set of stop ids that are interchanges — a stop served by two or more
/// distinct routes in [routeStations]. This is derived purely from the ordered
/// per-line sequences (route_id -> direction -> ordered stop ids), never
/// hard-coded, so it stays correct as the feed changes.
Set<String> detectInterchanges(
  Map<String, Map<String, List<String>>> routeStations,
) {
  final routesByStop = <String, Set<String>>{};
  routeStations.forEach((routeId, byDirection) {
    for (final sequence in byDirection.values) {
      for (final stopId in sequence) {
        (routesByStop[stopId] ??= <String>{}).add(routeId);
      }
    }
  });
  return {
    for (final entry in routesByStop.entries)
      if (entry.value.length >= 2) entry.key,
  };
}

/// The number of distinct routes serving each stop id — the underlying count
/// [detectInterchanges] thresholds on, exposed for callers that want the raw
/// figure (e.g. sizing a marker by how many lines meet).
Map<String, int> routeCountByStop(
  Map<String, Map<String, List<String>>> routeStations,
) {
  final routesByStop = <String, Set<String>>{};
  routeStations.forEach((routeId, byDirection) {
    for (final sequence in byDirection.values) {
      for (final stopId in sequence) {
        (routesByStop[stopId] ??= <String>{}).add(routeId);
      }
    }
  });
  return {for (final entry in routesByStop.entries) entry.key: entry.value.length};
}

/// The representative ordered stop-id sequence to draw a route's polyline
/// from: direction "0" when present (the canonical forward direction), else
/// the first available direction. Mirrors how the live map picks a line's
/// geometry so the schematic and the live map never disagree. Null when the
/// route has no drawable (>= 2 stop) sequence.
List<String>? routeDrawSequence(Map<String, List<String>> byDirection) {
  final sequence = byDirection['0'] ??
      (byDirection.isEmpty ? null : byDirection.values.first);
  if (sequence == null || sequence.length < 2) return null;
  return sequence;
}
