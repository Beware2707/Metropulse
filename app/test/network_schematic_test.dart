import 'dart:convert';
import 'dart:ui' show Offset, Size;

import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/network_schematic.dart';

/// A miniature but structurally complete fixture, mirroring the real asset
/// contract: 4 drawn lines across 3 lineKeys (BLUE has a main trunk and a
/// branch sharing the key), 9 stations, one interchange (R2), one -45 label
/// (R3), and non-station bend vertices on RED and the BLUE branch.
const String _fixtureJson = '''
{
  "version": 1,
  "canvas": {"width": 1000.0, "height": 800.0},
  "stations": {
    "R1": {"x": 100.0, "y": 100.0, "label": "Rithala", "labelAnchor": "n", "labelAngle": 0, "interchange": false},
    "R2": {"x": 300.0, "y": 100.0, "label": "Kashmere Gate", "labelAnchor": "ne", "labelAngle": 0, "interchange": true},
    "R3": {"x": 500.0, "y": 200.0, "label": "Shastri Park", "labelAnchor": "e", "labelAngle": -45, "interchange": false},
    "R4": {"x": 700.0, "y": 200.0, "label": "Dilshad Garden", "labelAnchor": "e", "labelAngle": 0, "interchange": false},
    "B1": {"x": 300.0, "y": 500.0, "label": "Dwarka", "labelAnchor": "s", "labelAngle": 0, "interchange": false},
    "BM": {"x": 300.0, "y": 300.0, "label": "Yamuna Bank", "labelAnchor": "w", "labelAngle": 0, "interchange": false},
    "BB1": {"x": 450.0, "y": 550.0, "label": "Noida City Centre", "labelAnchor": "se", "labelAngle": 0, "interchange": false},
    "G1": {"x": 700.0, "y": 600.0, "label": "Brigadier Hoshiar Singh", "labelAnchor": "sw", "labelAngle": 0, "interchange": false},
    "G2": {"x": 700.0, "y": 400.0, "label": "Bahadurgarh City", "labelAnchor": "e", "labelAngle": 0, "interchange": false}
  },
  "lines": [
    {
      "lineKey": "RED",
      "routeIds": ["0", "18"],
      "color": "#E53935",
      "points": [[100.0, 100.0], [300.0, 100.0], [400.0, 200.0], [500.0, 200.0], [700.0, 200.0]],
      "stopIds": ["R1", "R2", "R3", "R4"],
      "stopPointIndex": [0, 1, 3, 4]
    },
    {
      "lineKey": "BLUE",
      "routeIds": ["2", "20"],
      "color": "#0056A8",
      "points": [[300.0, 500.0], [300.0, 300.0], [300.0, 100.0]],
      "stopIds": ["B1", "BM", "R2"],
      "stopPointIndex": [0, 1, 2]
    },
    {
      "lineKey": "BLUE",
      "routeIds": ["3"],
      "color": "#0056A8",
      "points": [[300.0, 300.0], [450.0, 450.0], [450.0, 550.0]],
      "stopIds": ["BM", "BB1"],
      "stopPointIndex": [0, 2]
    },
    {
      "lineKey": "GREEN",
      "routeIds": ["4"],
      "color": "#00A651",
      "points": [[700.0, 600.0], [700.0, 400.0], [700.0, 200.0]],
      "stopIds": ["G1", "G2", "R4"],
      "stopPointIndex": [0, 1, 2]
    }
  ]
}
''';

Map<String, dynamic> _fixtureMap() => jsonDecode(_fixtureJson) as Map<String, dynamic>;

void main() {
  group('NetworkSchematic.fromJson', () {
    test('parses the full contract round-trip', () {
      final schematic = NetworkSchematic.parse(_fixtureJson);

      expect(schematic.version, 1);
      expect(schematic.canvas, const Size(1000, 800));
      expect(schematic.stations.length, 9);
      expect(schematic.lines.length, 4);

      final r2 = schematic.stations['R2']!;
      expect(r2.position, const Offset(300, 100));
      expect(r2.interchange, isTrue);
      expect(r2.labelAnchor, SchematicLabelAnchor.ne);
      expect(r2.label, 'Kashmere Gate');
      expect(r2.labelAngle, 0);

      final r3 = schematic.stations['R3']!;
      expect(r3.labelAngle, -45);
      expect(r3.labelAnchor, SchematicLabelAnchor.e);
      expect(r3.interchange, isFalse);

      final red = schematic.lines.first;
      expect(red.lineKey, 'RED');
      expect(red.routeIds, ['0', '18']);
      expect(red.color, '#E53935');
      expect(red.points, hasLength(5));
      expect(red.points[2], const Offset(400, 200)); // the non-station bend
      expect(red.stopIds, ['R1', 'R2', 'R3', 'R4']);
      expect(red.stopPointIndex, [0, 1, 3, 4]);
    });

    test('a branch may share a lineKey with different routeIds', () {
      final schematic = NetworkSchematic.parse(_fixtureJson);
      final blues = schematic.lines.where((l) => l.lineKey == 'BLUE').toList();
      expect(blues, hasLength(2));
      expect(blues[0].routeIds, isNot(equals(blues[1].routeIds)));
    });

    test('throws on stopPointIndex length mismatch', () {
      final json = _fixtureMap();
      ((json['lines'] as List)[0] as Map<String, dynamic>)['stopPointIndex'] = [0, 1, 3];
      expect(() => NetworkSchematic.fromJson(json), throwsFormatException);
    });

    test('throws when a line references a stop missing from stations', () {
      final json = _fixtureMap();
      (json['stations'] as Map<String, dynamic>).remove('R3');
      expect(() => NetworkSchematic.fromJson(json), throwsFormatException);
    });

    test('throws when stopPointIndex points outside points[]', () {
      final json = _fixtureMap();
      ((json['lines'] as List)[0] as Map<String, dynamic>)['stopPointIndex'] = [0, 1, 3, 99];
      expect(() => NetworkSchematic.fromJson(json), throwsFormatException);
    });

    test('throws when canvas is absent', () {
      final json = _fixtureMap()..remove('canvas');
      expect(() => NetworkSchematic.fromJson(json), throwsFormatException);
    });
  });

  group('positionOf', () {
    test('returns the design-space position of a known stop', () {
      final schematic = NetworkSchematic.parse(_fixtureJson);
      expect(schematic.positionOf('R1'), const Offset(100, 100));
      expect(schematic.positionOf('BB1'), const Offset(450, 550));
    });

    test('is null for a stop the asset does not know', () {
      final schematic = NetworkSchematic.parse(_fixtureJson);
      expect(schematic.positionOf('NEW_STATION_2027'), isNull);
    });
  });

  group('segmentBetween', () {
    late NetworkSchematic schematic;

    setUp(() => schematic = NetworkSchematic.parse(_fixtureJson));

    test('forward slice by lineKey includes the non-station bend vertex', () {
      final segment = schematic.segmentBetween('RED', 'R2', 'R4');
      expect(segment, const [
        Offset(300, 100),
        Offset(400, 200), // bend — not a station, but part of the drawn path
        Offset(500, 200),
        Offset(700, 200),
      ]);
    });

    test('forward slice by directional routeId', () {
      final segment = schematic.segmentBetween('18', 'R1', 'R3');
      expect(segment, const [
        Offset(100, 100),
        Offset(300, 100),
        Offset(400, 200),
        Offset(500, 200),
      ]);
    });

    test('reversed slice (from a later stop to an earlier one) is reversed, bends included', () {
      final forward = schematic.segmentBetween('RED', 'R2', 'R4')!;
      final backward = schematic.segmentBetween('RED', 'R4', 'R2')!;
      expect(backward, forward.reversed.toList());
      expect(backward.first, const Offset(700, 200));
      expect(backward.last, const Offset(300, 100));
    });

    test('resolves to the branch that actually contains both stops', () {
      // BB1 lives only on the BLUE branch; the trunk (also lineKey BLUE and
      // listed first) must be skipped, not returned with a missing stop.
      final segment = schematic.segmentBetween('BLUE', 'BM', 'BB1');
      expect(segment, const [
        Offset(300, 300),
        Offset(450, 450), // branch bend vertex
        Offset(450, 550),
      ]);
      // And the trunk still resolves for trunk-only stop pairs.
      expect(schematic.segmentBetween('BLUE', 'B1', 'R2'), const [
        Offset(300, 500),
        Offset(300, 300),
        Offset(300, 100),
      ]);
    });

    test('single-station slice degenerates to one point', () {
      expect(schematic.segmentBetween('GREEN', 'G2', 'G2'), const [Offset(700, 400)]);
    });

    test('is null when no drawn line matches the key or holds both stops', () {
      expect(schematic.segmentBetween('PONY', 'R1', 'R2'), isNull);
      // Both stops exist, but on different lines.
      expect(schematic.segmentBetween('RED', 'R1', 'B1'), isNull);
      expect(schematic.segmentBetween('BLUE', 'B1', 'BB1'), isNull);
    });
  });
}
