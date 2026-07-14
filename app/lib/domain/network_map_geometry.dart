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

/// The physical-line identity key for a GTFS route.
///
/// The real DMRC feed models each travel *direction* as a separate route row:
/// route_long_name 'RED_Rithala to Dilshad Garden' and
/// 'RED_Dilshad Garden  to Rithala' are two distinct route_ids that are the
/// same physical Red line, just reversed. And every `route_color` in that
/// feed is empty, so the long-name prefix before the first underscore ('RED',
/// 'PINK', 'MAGENTA', 'VIOLET', 'YELLOW', 'GREEN', 'AQUA', 'GRAY', 'RAPID')
/// is the *only* carrier of line identity — the same prefix `routeColor()`
/// in theme.dart already keys line colours from.
///
/// Note the short_name prefix would be the WRONG thing to parse: 'R_SP_R' is
/// the RAPID line and 'R_RD' is the RED line — both start with 'R_'. Always
/// feed this function the long name.
///
/// Returns, in order of preference:
/// - the uppercased, trimmed prefix of [longName] before the first
///   underscore, when [longName] has an underscore with a non-empty prefix;
/// - the whole uppercased, trimmed [longName] when it is non-empty but has no
///   usable underscore prefix;
/// - [routeId] itself when [longName] is null or blank (each route then
///   stays its own "line", the pre-existing behaviour).
String lineKeyForRoute(String routeId, String? longName) {
  final name = longName?.trim() ?? '';
  if (name.isEmpty) return routeId;
  final underscore = name.indexOf('_');
  if (underscore > 0) {
    return name.substring(0, underscore).trim().toUpperCase();
  }
  return name.toUpperCase();
}

/// The set of stop ids that are interchanges — a stop served by two or more
/// distinct *lines*. Derived purely from the ordered per-route sequences
/// (route_id -> direction -> ordered stop ids), never hard-coded, so it stays
/// correct as the feed changes.
///
/// Without [lineKeyByRoute] a "line" is a raw route_id. That is only correct
/// for feeds where one physical line is one route row. The real DMRC feed
/// models each travel direction as its own route (36 route rows, in
/// reversed pairs like 'RED_Rithala to Dilshad Garden' /
/// 'RED_Dilshad Garden  to Rithala'), so counting route_ids flags every
/// single stop as an interchange — its two directions look like two routes.
/// Pass [lineKeyByRoute] (route_id -> line key, built with [lineKeyForRoute])
/// to count distinct physical lines instead: route_ids that map to the same
/// line key count as ONE line.
Set<String> detectInterchanges(
  Map<String, Map<String, List<String>>> routeStations, {
  Map<String, String>? lineKeyByRoute,
}) {
  final linesByStop = _lineKeysByStop(routeStations, lineKeyByRoute);
  return {
    for (final entry in linesByStop.entries)
      if (entry.value.length >= 2) entry.key,
  };
}

/// The number of distinct lines serving each stop id — the underlying count
/// [detectInterchanges] thresholds on, exposed for callers that want the raw
/// figure (e.g. sizing a marker by how many lines meet).
///
/// [lineKeyByRoute] has the same meaning as in [detectInterchanges]: without
/// it each route_id counts separately (wrong for the direction-as-route DMRC
/// feed, where every stop is then served by >= 2 route_ids); with it,
/// route_ids sharing a line key count as one line.
Map<String, int> routeCountByStop(
  Map<String, Map<String, List<String>>> routeStations, {
  Map<String, String>? lineKeyByRoute,
}) {
  final linesByStop = _lineKeysByStop(routeStations, lineKeyByRoute);
  return {for (final entry in linesByStop.entries) entry.key: entry.value.length};
}

/// Shared accumulator: the set of line keys (or raw route_ids when
/// [lineKeyByRoute] is absent) serving each stop.
Map<String, Set<String>> _lineKeysByStop(
  Map<String, Map<String, List<String>>> routeStations,
  Map<String, String>? lineKeyByRoute,
) {
  final linesByStop = <String, Set<String>>{};
  routeStations.forEach((routeId, byDirection) {
    final lineKey = lineKeyByRoute?[routeId] ?? routeId;
    for (final sequence in byDirection.values) {
      for (final stopId in sequence) {
        (linesByStop[stopId] ??= <String>{}).add(lineKey);
      }
    }
  });
  return linesByStop;
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
