import 'dart:convert';
import 'dart:ui' show Offset, Size;

import 'package:flutter/services.dart' show rootBundle;

/// Which side of a station dot its label sits on. Precomputed by the layout
/// tool so labels are collision-free by construction — the renderer just
/// honours the anchor, it never re-declutters asset labels at runtime.
enum SchematicLabelAnchor { e, w, n, s, ne, nw, se, sw }

SchematicLabelAnchor _anchorFromString(String? value) {
  switch (value) {
    case 'w':
      return SchematicLabelAnchor.w;
    case 'n':
      return SchematicLabelAnchor.n;
    case 's':
      return SchematicLabelAnchor.s;
    case 'ne':
      return SchematicLabelAnchor.ne;
    case 'nw':
      return SchematicLabelAnchor.nw;
    case 'se':
      return SchematicLabelAnchor.se;
    case 'sw':
      return SchematicLabelAnchor.sw;
    case 'e':
    default:
      // Lenient on unknown values: 'e' is the classic metro-map default and a
      // wrong-but-drawn label beats a hard parse failure for one station.
      return SchematicLabelAnchor.e;
  }
}

/// One station of the precomputed schematic: a design-space position plus
/// everything needed to draw its label without any runtime layout decisions.
class SchematicStation {
  const SchematicStation({
    required this.x,
    required this.y,
    required this.label,
    required this.labelAnchor,
    required this.labelAngle,
    required this.interchange,
    this.labelDx,
    this.labelDy,
  });

  factory SchematicStation.fromJson(Map<String, dynamic> json) {
    final x = json['x'];
    final y = json['y'];
    if (x is! num || y is! num) {
      throw const FormatException('schematic station is missing numeric x/y');
    }
    return SchematicStation(
      x: x.toDouble(),
      y: y.toDouble(),
      label: (json['label'] as String?) ?? '',
      labelAnchor: _anchorFromString(json['labelAnchor'] as String?),
      labelAngle: ((json['labelAngle'] as num?) ?? 0).toDouble(),
      interchange: (json['interchange'] as bool?) ?? false,
      labelDx: (json['labelDx'] as num?)?.toDouble(),
      labelDy: (json['labelDy'] as num?)?.toDouble(),
    );
  }

  final double x;
  final double y;
  final String label;
  final SchematicLabelAnchor labelAnchor;

  /// Degrees. 0 for horizontal, -45 for the rotated up-right labels the tool
  /// emits in tight areas.
  final double labelAngle;
  final bool interchange;

  /// Exact label-box origin relative to the station, as collision-checked by
  /// the layout tool. When present the renderer places the label box here
  /// verbatim (top-left corner for angle 0; rotation pivot for -45), so the
  /// tool's zero-overlap guarantee carries to the device. Older assets
  /// without these fall back to anchor-derived offsets.
  final double? labelDx;
  final double? labelDy;

  Offset get position => Offset(x, y);
}

/// One drawn line (branch): the full octilinear polyline including the
/// non-station bend vertices, plus the ordered stations along it and where
/// each station sits inside [points].
class SchematicLine {
  const SchematicLine({
    required this.lineKey,
    required this.routeIds,
    required this.color,
    required this.points,
    required this.stopIds,
    required this.stopPointIndex,
  });

  factory SchematicLine.fromJson(Map<String, dynamic> json) {
    final rawPoints = json['points'];
    if (rawPoints is! List) {
      throw const FormatException('schematic line has no points array');
    }
    final points = <Offset>[
      for (final p in rawPoints)
        if (p is List && p.length >= 2 && p[0] is num && p[1] is num)
          Offset((p[0] as num).toDouble(), (p[1] as num).toDouble())
        else
          throw const FormatException('schematic line point is not an [x, y] pair'),
    ];
    final stopIds = [for (final id in (json['stopIds'] as List? ?? const [])) id.toString()];
    final rawIndex = json['stopPointIndex'] as List? ?? const [];
    final stopPointIndex = <int>[
      for (final i in rawIndex)
        if (i is num) i.toInt() else throw const FormatException('stopPointIndex entry is not a number'),
    ];
    return SchematicLine(
      lineKey: (json['lineKey'] as String?) ?? '',
      routeIds: [for (final id in (json['routeIds'] as List? ?? const [])) id.toString()],
      color: json['color'] as String?,
      points: points,
      stopIds: stopIds,
      stopPointIndex: stopPointIndex,
    );
  }

  /// Long-name prefix ('RED', 'BLUE', …) — the same key `lineKeyForRoute`
  /// derives from GTFS long names, so legs match drawn lines either way.
  final String lineKey;

  /// The directional GTFS route_ids this single drawn branch covers.
  final List<String> routeIds;

  /// Tool-chosen hex (e.g. '#E53935'); the renderer still passes it through
  /// `routeColor()` so the theme's name-keyed table remains the fallback.
  final String? color;

  /// The full drawn polyline, bends included, in design-space coordinates.
  final List<Offset> points;

  /// Ordered stations along this branch.
  final List<String> stopIds;

  /// For each entry of [stopIds], the index into [points] where that station
  /// sits — what lets a journey leg slice out the exact drawn geometry.
  final List<int> stopPointIndex;
}

/// The parsed `assets/network_schematic.json`: a precomputed, designed
/// octilinear metro map in its own design space (roughly 2400 x 2600-3000).
class NetworkSchematic {
  const NetworkSchematic({
    required this.version,
    required this.canvas,
    required this.stations,
    required this.lines,
  });

  /// Parses and validates the asset. Throws [FormatException] on structural
  /// problems (missing canvas, stopIds/stopPointIndex mismatches, stations
  /// referenced by a line but absent from the stations map, point indices out
  /// of range) so a broken asset fails loudly into the geographic fallback
  /// instead of drawing garbage.
  factory NetworkSchematic.fromJson(Map<String, dynamic> json) {
    final canvasJson = json['canvas'];
    if (canvasJson is! Map<String, dynamic> ||
        canvasJson['width'] is! num ||
        canvasJson['height'] is! num) {
      throw const FormatException('schematic has no canvas width/height');
    }
    final stationsJson = json['stations'];
    if (stationsJson is! Map<String, dynamic>) {
      throw const FormatException('schematic has no stations map');
    }
    final stations = <String, SchematicStation>{
      for (final entry in stationsJson.entries)
        entry.key: SchematicStation.fromJson(entry.value as Map<String, dynamic>),
    };
    final linesJson = json['lines'];
    if (linesJson is! List) {
      throw const FormatException('schematic has no lines array');
    }
    final lines = [
      for (final line in linesJson) SchematicLine.fromJson(line as Map<String, dynamic>),
    ];

    // Cross-referential integrity — the renderer indexes freely off these, so
    // they are verified once here rather than defensively everywhere.
    for (final line in lines) {
      if (line.stopIds.length != line.stopPointIndex.length) {
        throw FormatException(
            'line ${line.lineKey}: stopPointIndex length ${line.stopPointIndex.length} '
            '!= stopIds length ${line.stopIds.length}');
      }
      for (final stopId in line.stopIds) {
        if (!stations.containsKey(stopId)) {
          throw FormatException('line ${line.lineKey}: stop $stopId missing from stations');
        }
      }
      for (final index in line.stopPointIndex) {
        if (index < 0 || index >= line.points.length) {
          throw FormatException(
              'line ${line.lineKey}: stopPointIndex $index out of range for '
              '${line.points.length} points');
        }
      }
    }

    return NetworkSchematic(
      version: (json['version'] as num?)?.toInt() ?? 1,
      canvas: Size(
        (canvasJson['width'] as num).toDouble(),
        (canvasJson['height'] as num).toDouble(),
      ),
      stations: stations,
      lines: lines,
    );
  }

  /// [NetworkSchematic.fromJson] from a raw JSON string. Top-level-callable,
  /// so it is `compute()`-friendly should parsing ever need an isolate.
  static NetworkSchematic parse(String jsonString) =>
      NetworkSchematic.fromJson(jsonDecode(jsonString) as Map<String, dynamic>);

  /// Loads the bundled asset. Throws (asset missing, malformed JSON, failed
  /// validation) rather than degrading silently — the caller's AsyncValue
  /// error state is the geographic-fallback switch.
  static Future<NetworkSchematic> loadFromAsset() async {
    final raw = await rootBundle.loadString('assets/network_schematic.json');
    return parse(raw);
  }

  final int version;

  /// Design-space size the coordinates live in — the CustomPaint canvas size.
  final Size canvas;
  final Map<String, SchematicStation> stations;
  final List<SchematicLine> lines;

  /// The design-space position of a station, or null when the asset does not
  /// know the stop (e.g. a station added to the GTFS feed after the asset was
  /// generated — the renderer places those via an affine geo fit instead).
  Offset? positionOf(String stopId) => stations[stopId]?.position;

  /// The drawn polyline between two stations on the line identified by
  /// [lineKeyOrRouteId] (matched against each line's routeIds first, then its
  /// lineKey), sliced out of points[] via stopPointIndex so it follows the
  /// exact drawn bends — inclusive of both stations, reversed when [fromStopId]
  /// sits later along the line than [toStopId]. Null when no single drawn line
  /// matches the key and contains both stops (caller falls back to straight
  /// station-to-station segments).
  List<Offset>? segmentBetween(String lineKeyOrRouteId, String fromStopId, String toStopId) {
    for (final line in lines) {
      if (line.lineKey != lineKeyOrRouteId && !line.routeIds.contains(lineKeyOrRouteId)) {
        continue;
      }
      final fromIndex = line.stopIds.indexOf(fromStopId);
      final toIndex = line.stopIds.indexOf(toStopId);
      // A branch sharing the lineKey may hold only one of the two stops —
      // keep looking, a sibling branch may hold both.
      if (fromIndex < 0 || toIndex < 0) continue;
      final a = line.stopPointIndex[fromIndex];
      final b = line.stopPointIndex[toIndex];
      final slice = line.points.sublist(a < b ? a : b, (a < b ? b : a) + 1);
      return a <= b ? slice : slice.reversed.toList();
    }
    return null;
  }
}
