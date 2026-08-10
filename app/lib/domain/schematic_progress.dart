// Where to draw the train on the schematic map, and which way it faces.
//
// The schematic is a DIAGRAM: lines are straightened to 45° angles and spacing
// is even, so its geometry is deliberately not geographic. That has a direct
// honesty consequence — plotting a raw GPS coordinate onto it would place the
// marker somewhere that means nothing, while looking exactly as authoritative
// as a surveyed position.
//
// So the marker is driven by what we actually know: which stations the rider
// has passed, and how far along the current hop they are. "Between Mandi House
// and Supreme Court, about a third of the way" is a true statement about the
// journey, and it is the statement the schematic is built to show.

import 'dart:math' as math;

/// A point on the schematic canvas (diagram space, not lat/lon).
class SchematicPoint {
  const SchematicPoint(this.x, this.y);

  final double x;
  final double y;

  @override
  String toString() => 'SchematicPoint(${x.toStringAsFixed(1)}, '
      '${y.toStringAsFixed(1)})';
}

/// Where the train marker goes, and its heading.
class TrainMarker {
  const TrainMarker({
    required this.position,
    required this.headingRadians,
    required this.isStationary,
  });

  final SchematicPoint position;

  /// Direction of travel, for orienting the train body. A train drawn as a
  /// rounded bar pointing the wrong way reads as a mistake immediately, even
  /// to someone who could not say why.
  final double headingRadians;

  /// True when sitting at a station — the marker should stop bobbing.
  final bool isStationary;
}

/// Places the train along a route drawn as [stationPoints] in schematic space.
///
/// [reachedIndex] is the last station confirmed passed (-1 before the first).
/// [hopFraction] is 0..1 progress from that station to the next; callers pass
/// 0 when they only know the station and not the distance between — which is
/// the normal case underground, and produces a train sitting at the platform
/// rather than a fabricated position mid-tunnel.
TrainMarker? trainMarkerFor({
  required List<SchematicPoint> stationPoints,
  required int reachedIndex,
  double hopFraction = 0,
}) {
  if (stationPoints.length < 2) return null;

  final from = reachedIndex.clamp(-1, stationPoints.length - 1);
  // Before the first station the train is AT the origin, not off the map.
  final startIndex = from < 0 ? 0 : from;
  final endIndex = math.min(startIndex + 1, stationPoints.length - 1);

  final start = stationPoints[startIndex];
  final end = stationPoints[endIndex];

  // At the terminus there is no next hop to interpolate into.
  final atEnd = startIndex == endIndex;
  final t = atEnd ? 0.0 : hopFraction.clamp(0.0, 1.0);

  final position = SchematicPoint(
    start.x + (end.x - start.x) * t,
    start.y + (end.y - start.y) * t,
  );

  // Heading from the segment, not from the marker's own movement: a stationary
  // train still faces the way it is going, and atan2 of a zero-length delta
  // would otherwise snap it to an arbitrary angle.
  final heading = atEnd
      ? 0.0
      : math.atan2(end.y - start.y, end.x - start.x);

  return TrainMarker(
    position: position,
    headingRadians: heading,
    // Exactly at a platform: at the start of a hop, or at the terminus.
    isStationary: atEnd || t <= 0.001,
  );
}

/// How far along the current hop the rider is, from a real distance.
///
/// Returns null when there is no usable distance — which must render as "at
/// the last known station", never as a guessed midpoint. [metresToNext] comes
/// only from a position fix; a timetable cannot supply it.
double? hopFractionFromDistance({
  required double? metresToNext,
  required double hopLengthMetres,
}) {
  if (metresToNext == null || hopLengthMetres <= 0) return null;
  final travelled = hopLengthMetres - metresToNext;
  return (travelled / hopLengthMetres).clamp(0.0, 1.0);
}

/// The camera target when a journey starts: the origin station, so the rider
/// sees where they are boarding rather than the whole network.
SchematicPoint? journeyStartFocus(List<SchematicPoint> stationPoints) =>
    stationPoints.isEmpty ? null : stationPoints.first;
