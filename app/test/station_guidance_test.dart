// Phase-aware station guidance.
//
// The behaviours pinned here are the ones that would hurt a real person:
//   * escalators are never mentioned (no dataset has a single one);
//   * "step-free not mapped" is never phrased as "not accessible";
//   * a step-free need outranks landmark convenience;
//   * gate 12 never matches gate 1 or 2 — a wrong accessible badge sends a
//     wheelchair user to a staircase;
//   * absent data produces no guidance, not filler.
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/station_guidance.dart';

const _accessible = <String, dynamic>{
  'step_free_gates': [
    {'id': 'g2', 'name': 'Gate No. 2'},
    {'id': 'g5', 'name': 'Gate No. 5'},
  ],
};
const _mappedButNoStepFree = <String, dynamic>{
  'step_free_gates': <Map<String, dynamic>>[],
};

final _exits = <Map<String, dynamic>>[
  {'name': 'Gate No. 1', 'landmarks': ['Red Fort', 'Chandni Chowk', 'Jain Mandir']},
  {'name': 'Gate No. 3', 'landmarks': ['Town Hall']},
];

void main() {
  group('phase changes what a gate means', () {
    test('the same station reads enter / change / leave by phase', () {
      String headlineFor(JourneyPhase phase) => buildStationGuidance(
            phase: phase,
            stepFreePreferred: false,
            exits: _exits,
          )!.headline;

      expect(headlineFor(JourneyPhase.enteringOrigin), 'Enter at Gate No. 1');
      expect(headlineFor(JourneyPhase.approachingInterchange),
          'Change at Gate No. 1');
      expect(headlineFor(JourneyPhase.arriving), 'Leave by Gate No. 1');
    });

    test('mid-ride there is nothing to act on, so nothing is said', () {
      expect(
        buildStationGuidance(
          phase: JourneyPhase.riding,
          stepFreePreferred: false,
          exits: _exits,
        ),
        isNull,
      );
    });

    test('the exit with the most landmarks leads — that is how people navigate',
        () {
      final g = buildStationGuidance(
        phase: JourneyPhase.arriving,
        stepFreePreferred: false,
        exits: _exits,
      )!;
      expect(g.headline, contains('Gate No. 1'));
      expect(g.landmarkNote, 'Closest to Red Fort, Chandni Chowk');
    });
  });

  group('step-free need outranks convenience', () {
    test('a step-free rider is sent to the mapped lift gate, not the landmark one',
        () {
      final g = buildStationGuidance(
        phase: JourneyPhase.enteringOrigin,
        stepFreePreferred: true,
        exits: _exits,
        accessibility: _accessible,
      )!;
      expect(g.headline, 'Enter at Gate No. 2, Gate No. 5');
      expect(g.stepFree, isTrue);
      expect(g.headline, isNot(contains('Gate No. 1')),
          reason: 'the landmark-rich gate is not the lift-served one');
    });

    test('unmapped reads as "not mapped", never "not accessible"', () {
      final g = buildStationGuidance(
        phase: JourneyPhase.arriving,
        stepFreePreferred: true,
        exits: _exits,
        accessibility: _mappedButNoStepFree,
      )!;
      expect(g.stepFreeUnmapped, isTrue);
      expect(g.headline, contains('not mapped'));
      expect(g.headline.toLowerCase(), isNot(contains('not accessible')));
      expect(g.landmarkNote, contains('155370'),
          reason: 'a gap in the data needs a human to call');
    });

    test('no accessibility data at all stays silent rather than alarming', () {
      expect(
        buildStationGuidance(
          phase: JourneyPhase.arriving,
          stepFreePreferred: true,
          exits: _exits,
        ),
        isNull,
      );
    });
  });

  group('the matched exit from the engine wins when arriving', () {
    test('a landmark-matched exit is used verbatim', () {
      final g = buildStationGuidance(
        phase: JourneyPhase.arriving,
        stepFreePreferred: false,
        exits: _exits,
        matchedExitName: 'Gate No. 5',
        matchedLandmark: 'Jama Masjid',
        accessibility: _accessible,
      )!;
      expect(g.headline, 'Leave by Gate No. 5');
      expect(g.landmarkNote, 'Closest to Jama Masjid');
      expect(g.stepFree, isTrue, reason: 'Gate 5 is in the step-free set');
    });
  });

  group('gate matching is exact', () {
    test('gate 12 never matches gate 1 or 2', () {
      expect(exitIsStepFree('Gate No. 12', _accessible), isFalse);
      expect(exitIsStepFree('Gate No. 2', _accessible), isTrue);
    });

    test('a gate with no number never matches', () {
      expect(exitIsStepFree('Main Entrance', _accessible), isFalse);
    });

    test('different naming styles still join on the number', () {
      expect(exitIsStepFree('Chandni Chowk Metro Gate No. 5', _accessible),
          isTrue);
    });
  });

  group('escalators are never invented', () {
    test('no phase or preference produces the word "escalator"', () {
      for (final phase in JourneyPhase.values) {
        for (final stepFree in [true, false]) {
          final g = buildStationGuidance(
            phase: phase,
            stepFreePreferred: stepFree,
            exits: _exits,
            accessibility: _accessible,
            matchedExitName: 'Gate No. 2',
          );
          final text = '${g?.headline ?? ''} ${g?.detailLines.join(' ') ?? ''}'
              .toLowerCase();
          expect(text.contains('escalator'), isFalse,
              reason: 'no approved dataset contains a single escalator node');
        }
      }
    });
  });

  group('the lift claim is pitched at its evidence', () {
    test('a graph-confirmed gate gets the promise', () {
      final g = buildStationGuidance(
        phase: JourneyPhase.arriving,
        stepFreePreferred: false,
        exits: _exits,
        accessibility: {..._accessible, 'lifts': [{}, {}]},
        matchedExitName: 'Gate No. 2',
      )!;
      expect(g.liftNote, 'Lift to the platform');
      expect(g.stepFree, isTrue);
    });

    test('lifts exist but this gate is unconnected: a fact, not a promise', () {
      final g = buildStationGuidance(
        phase: JourneyPhase.arriving,
        stepFreePreferred: false,
        exits: _exits,
        accessibility: {'step_free_gates': const [], 'lifts': [{}, {}]},
        matchedExitName: 'Gate No. 9',
      )!;
      expect(g.liftNote, contains('2 lifts at this station'));
      expect(g.liftNote, contains('not mapped'));
      expect(g.stepFree, isFalse,
          reason: 'no tick without a mapped path from THIS gate');
    });

    test('no lift data at all says nothing about lifts', () {
      final g = buildStationGuidance(
        phase: JourneyPhase.arriving,
        stepFreePreferred: false,
        exits: _exits,
        matchedExitName: 'Gate No. 1',
      )!;
      expect(g.liftNote, isNull);
    });
  });

  group('platforms are named on the way in, not on the way out', () {
    Map<String, dynamic> withPlatforms() => {
          ..._accessible,
          'platforms': [
            {'name': 'Platform 1'},
            {'name': 'Platform 2'},
          ],
        };

    test('entering the station names the platforms', () {
      final g = buildStationGuidance(
        phase: JourneyPhase.enteringOrigin,
        stepFreePreferred: false,
        exits: _exits,
        accessibility: withPlatforms(),
      )!;
      expect(g.platformNote, 'Platform 1, Platform 2 at this station');
    });

    test('arriving does not — they are behind the rider', () {
      final g = buildStationGuidance(
        phase: JourneyPhase.arriving,
        stepFreePreferred: false,
        exits: _exits,
        accessibility: withPlatforms(),
        matchedExitName: 'Gate No. 2',
      )!;
      expect(g.platformNote, isNull);
    });

    test('a platform is never tied to a direction — no data supports that', () {
      final g = buildStationGuidance(
        phase: JourneyPhase.enteringOrigin,
        stepFreePreferred: false,
        exits: _exits,
        accessibility: withPlatforms(),
      )!;
      final text = '${g.headline} ${g.detailLines.join(' ')}'.toLowerCase();
      expect(text.contains('towards'), isFalse);
      expect(text.contains('for '), isFalse,
          reason: 'no dataset maps a platform to a direction');
    });
  });

  group('empty data produces nothing', () {
    test('no exits and no accessibility yields no guidance', () {
      expect(
        buildStationGuidance(
          phase: JourneyPhase.enteringOrigin,
          stepFreePreferred: false,
        ),
        isNull,
      );
    });

    test('exits with no landmarks yield no guidance rather than a bare gate',
        () {
      expect(
        buildStationGuidance(
          phase: JourneyPhase.enteringOrigin,
          stepFreePreferred: false,
          exits: [
            {'name': 'Gate No. 4', 'landmarks': <String>[]},
          ],
        ),
        isNull,
      );
    });
  });
}
