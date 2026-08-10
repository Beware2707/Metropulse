// Placing the train on the schematic.
//
// The schematic is a diagram, not a map — lines are straightened and spacing
// is even. So the marker must be driven by which stations have been passed,
// never by a raw coordinate, and where we don't know the hop progress it must
// sit at the last known platform rather than invent a midpoint.
import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/schematic_progress.dart';

// A simple L: right along x, then down along y — enough to check heading.
const _route = [
  SchematicPoint(0, 0),
  SchematicPoint(100, 0),
  SchematicPoint(100, 100),
];

void main() {
  group('where the train sits', () {
    test('before the first station it waits AT the origin, not off the map',
        () {
      final marker = trainMarkerFor(stationPoints: _route, reachedIndex: -1);
      expect(marker!.position.x, 0);
      expect(marker.position.y, 0);
      expect(marker.isStationary, isTrue);
    });

    test('with no hop progress it sits at the last known platform', () {
      // Underground: we know the station, not the distance. Drawing it halfway
      // down the tunnel would be a picture of something we cannot see.
      final marker = trainMarkerFor(stationPoints: _route, reachedIndex: 0);
      expect(marker!.position.x, 0);
      expect(marker.isStationary, isTrue);
    });

    test('half a hop puts it halfway along that segment', () {
      final marker = trainMarkerFor(
          stationPoints: _route, reachedIndex: 0, hopFraction: 0.5);
      expect(marker!.position.x, 50);
      expect(marker.position.y, 0);
      expect(marker.isStationary, isFalse);
    });

    test('at the terminus it stops rather than running off the end', () {
      final marker = trainMarkerFor(
          stationPoints: _route, reachedIndex: 2, hopFraction: 0.9);
      expect(marker!.position.x, 100);
      expect(marker.position.y, 100);
      expect(marker.isStationary, isTrue);
    });

    test('a fraction outside 0..1 cannot push it past the next station', () {
      final marker = trainMarkerFor(
          stationPoints: _route, reachedIndex: 0, hopFraction: 4.0);
      expect(marker!.position.x, 100);
    });
  });

  group('which way it faces', () {
    test('heading follows the segment being travelled', () {
      final east = trainMarkerFor(
          stationPoints: _route, reachedIndex: 0, hopFraction: 0.3);
      expect(east!.headingRadians, closeTo(0, 1e-9)); // +x

      final south = trainMarkerFor(
          stationPoints: _route, reachedIndex: 1, hopFraction: 0.3);
      expect(south!.headingRadians, closeTo(math.pi / 2, 1e-9)); // +y
    });

    test('a stationary train still faces its direction of travel', () {
      // Zero-length delta would make atan2 snap to an arbitrary angle, and a
      // train drawn pointing the wrong way reads as broken instantly.
      final marker = trainMarkerFor(stationPoints: _route, reachedIndex: 0);
      expect(marker!.headingRadians, closeTo(0, 1e-9));
    });
  });

  group('hop fraction comes only from a real distance', () {
    test('a measured distance converts to progress', () {
      final t = hopFractionFromDistance(
          metresToNext: 300, hopLengthMetres: 1200);
      expect(t, closeTo(0.75, 1e-9));
    });

    test('no distance means no fraction — never a guessed midpoint', () {
      expect(
        hopFractionFromDistance(metresToNext: null, hopLengthMetres: 1200),
        isNull,
      );
    });

    test('a zero-length hop cannot divide by zero', () {
      expect(
        hopFractionFromDistance(metresToNext: 100, hopLengthMetres: 0),
        isNull,
      );
    });

    test('overshooting the station clamps rather than exceeding 1', () {
      final t =
          hopFractionFromDistance(metresToNext: -50, hopLengthMetres: 1000);
      expect(t, 1.0);
    });
  });

  group('camera', () {
    test('a starting journey focuses the origin station', () {
      final focus = journeyStartFocus(_route);
      expect(focus!.x, 0);
      expect(focus.y, 0);
    });

    test('an empty route has nothing to focus', () {
      expect(journeyStartFocus(const []), isNull);
    });

    test('a single-station route draws no train', () {
      expect(
        trainMarkerFor(
            stationPoints: const [SchematicPoint(0, 0)], reachedIndex: 0),
        isNull,
      );
    });
  });
}
