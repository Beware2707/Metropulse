import 'dart:ui' show Size;

import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/models/station.dart';
import 'package:metropulse_app/domain/network_map_geometry.dart';

const _stations = [
  // A rough NW / NE / SW / SE box around central Delhi.
  Station(stopId: 'NW', name: 'North West', lat: 28.70, lon: 77.10),
  Station(stopId: 'NE', name: 'North East', lat: 28.70, lon: 77.30),
  Station(stopId: 'SW', name: 'South West', lat: 28.50, lon: 77.10),
  Station(stopId: 'SE', name: 'South East', lat: 28.50, lon: 77.30),
  Station(stopId: 'MID', name: 'Middle', lat: 28.60, lon: 77.20),
];

// route A runs NW->NE->MID, route B runs SW->MID->SE. MID is on both.
const _routeStations = {
  'A': {
    '0': ['NW', 'NE', 'MID'],
    '1': ['MID', 'NE', 'NW'],
  },
  'B': {
    '0': ['SW', 'MID', 'SE'],
  },
};

void main() {
  group('GeoBounds.fromStations', () {
    test('computes the min/max lat/lon envelope', () {
      final bounds = GeoBounds.fromStations(_stations)!;
      expect(bounds.minLat, 28.50);
      expect(bounds.maxLat, 28.70);
      expect(bounds.minLon, 77.10);
      expect(bounds.maxLon, 77.30);
    });

    test('is null for an empty station set', () {
      expect(GeoBounds.fromStations(const <Station>[]), isNull);
    });
  });

  group('SchematicProjection', () {
    const size = Size(400, 600);
    const padding = 32.0;

    test('every station projects inside the padded canvas', () {
      final bounds = GeoBounds.fromStations(_stations)!;
      final projection = SchematicProjection(bounds: bounds, size: size, padding: padding);
      for (final station in _stations) {
        final point = projection.projectStation(station);
        expect(point.dx, inInclusiveRange(padding - 0.001, size.width - padding + 0.001));
        expect(point.dy, inInclusiveRange(padding - 0.001, size.height - padding + 0.001));
      }
    });

    test('north is up and east is right', () {
      final bounds = GeoBounds.fromStations(_stations)!;
      final projection = SchematicProjection(bounds: bounds, size: size, padding: padding);
      final nw = projection.projectStation(_stations[0]);
      final ne = projection.projectStation(_stations[1]);
      final sw = projection.projectStation(_stations[2]);

      // NE is to the right of NW (greater longitude -> greater x).
      expect(ne.dx, greaterThan(nw.dx));
      // SW is below NW (smaller latitude -> greater y, since y grows downward).
      expect(sw.dy, greaterThan(nw.dy));
      // NW and NE share a latitude, so they share a y.
      expect(ne.dy, closeTo(nw.dy, 0.001));
    });

    test('the geographic centre maps to the canvas centre', () {
      final bounds = GeoBounds.fromStations(_stations)!;
      final projection = SchematicProjection(bounds: bounds, size: size, padding: padding);
      final mid = projection.projectStation(_stations[4]); // 28.60, 77.20 — dead centre
      expect(mid.dx, closeTo(size.width / 2, 0.5));
      expect(mid.dy, closeTo(size.height / 2, 0.5));
    });

    test('a single station (zero-span bounds) centres without dividing by zero', () {
      const one = [Station(stopId: 'X', name: 'Only', lat: 28.6, lon: 77.2)];
      final bounds = GeoBounds.fromStations(one)!;
      final projection = SchematicProjection(bounds: bounds, size: size, padding: padding);
      final point = projection.projectStation(one.first);
      expect(point.dx, closeTo(size.width / 2, 0.5));
      expect(point.dy, closeTo(size.height / 2, 0.5));
    });
  });

  group('detectInterchanges', () {
    test('flags a stop served by two routes and not a stop served by one', () {
      final interchanges = detectInterchanges(_routeStations);
      expect(interchanges, contains('MID'));
      expect(interchanges, isNot(contains('NW')));
      expect(interchanges, isNot(contains('SE')));
    });

    test('a stop appearing only in different directions of one route is not an interchange', () {
      // 'NE' is in both directions of route A but no second route — not an interchange.
      final interchanges = detectInterchanges(_routeStations);
      expect(interchanges, isNot(contains('NE')));
    });

    test('empty input yields no interchanges', () {
      expect(detectInterchanges(const {}), isEmpty);
    });
  });

  group('routeCountByStop', () {
    test('counts distinct routes per stop', () {
      final counts = routeCountByStop(_routeStations);
      expect(counts['MID'], 2);
      expect(counts['NW'], 1);
      expect(counts['SE'], 1);
    });
  });

  group('lineKeyForRoute', () {
    test('is the uppercased, trimmed prefix before the first underscore', () {
      expect(lineKeyForRoute('1', 'RED_Rithala to Dilshad Garden'), 'RED');
      // The reversed direction of the same physical line — same key.
      expect(lineKeyForRoute('2', 'RED_Dilshad Garden  to Rithala'), 'RED');
      expect(lineKeyForRoute('3', 'magenta_Botanical Garden to Janakpuri'), 'MAGENTA');
      expect(lineKeyForRoute('4', '  YELLOW_Samaypur Badli to Millennium City '), 'YELLOW');
    });

    test('a name without an underscore becomes the whole uppercased name', () {
      expect(lineKeyForRoute('5', 'Airport Express'), 'AIRPORT EXPRESS');
    });

    test('an underscore with an empty prefix falls back to the full name', () {
      expect(lineKeyForRoute('6', '_odd'), '_ODD');
    });

    test('a null or blank long name falls back to the route id', () {
      expect(lineKeyForRoute('R9', null), 'R9');
      expect(lineKeyForRoute('R9', ''), 'R9');
      expect(lineKeyForRoute('R9', '   '), 'R9');
    });
  });

  group('direction-as-separate-route feeds (the real DMRC shape)', () {
    // The real feed models each travel direction as its own route_id:
    // 'R1'/'R1R' are one physical RED line, 'Y1' is a YELLOW line crossing
    // it at 'X'. Every route_color is empty, so the long-name prefix is the
    // only line identity.
    const routeStations = {
      'R1': {
        '0': ['A', 'B', 'X', 'C'],
      },
      'R1R': {
        '0': ['C', 'X', 'B', 'A'],
      },
      'Y1': {
        '0': ['P', 'X', 'Q'],
      },
    };

    final lineKeyByRoute = {
      'R1': lineKeyForRoute('R1', 'RED_A to B'),
      'R1R': lineKeyForRoute('R1R', 'RED_B to A'),
      'Y1': lineKeyForRoute('Y1', 'YELLOW_C to D'),
    };

    test('without lineKeyByRoute every shared stop wrongly looks like an interchange', () {
      // The historical failure mode: both directions of one line count as two
      // routes, so all of the line's stops get flagged.
      final interchanges = detectInterchanges(routeStations);
      expect(interchanges, containsAll(['A', 'B', 'C', 'X']));
    });

    test('with lineKeyByRoute only the true RED x YELLOW crossing is an interchange', () {
      final interchanges = detectInterchanges(
        routeStations,
        lineKeyByRoute: lineKeyByRoute,
      );
      expect(interchanges, {'X'});
    });

    test('routeCountByStop counts lines, not directional route rows', () {
      final counts = routeCountByStop(
        routeStations,
        lineKeyByRoute: lineKeyByRoute,
      );
      expect(counts['X'], 2); // RED + YELLOW
      expect(counts['A'], 1); // RED only, despite two route_ids
      expect(counts['B'], 1);
      expect(counts['C'], 1);
      expect(counts['P'], 1);
    });
  });

  group('routeDrawSequence', () {
    test('prefers direction 0', () {
      expect(routeDrawSequence(_routeStations['A']!), ['NW', 'NE', 'MID']);
    });

    test('falls back to the first direction when 0 is absent', () {
      final seq = routeDrawSequence({
        '1': ['P', 'Q', 'R'],
      });
      expect(seq, ['P', 'Q', 'R']);
    });

    test('rejects a degenerate single-stop sequence', () {
      expect(routeDrawSequence({'0': ['P']}), isNull);
      expect(routeDrawSequence(const {}), isNull);
    });
  });
}
