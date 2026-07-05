import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/journey_timetable.dart';
import 'package:metropulse_app/domain/models/journey.dart';

JourneyStop _stop(String id, String name) => JourneyStop(stopId: id, name: name);

JourneyPlan _singleLinePlan() {
  final departure = DateTime(2026, 1, 1, 8);
  return JourneyPlan(
    origin: _stop('S1', 'Alpha'),
    destination: _stop('S4', 'Delta'),
    departureAt: departure,
    expectedArrivalAt: departure,
    expectedTravelSeconds: 750,
    interchangeCount: 0,
    interchangeStopIds: const [],
    walkingDistanceM: 0,
    remainingStations: const [],
    legs: [
      JourneyLeg(
        kind: 'ride',
        board: _stop('S1', 'Alpha'),
        alight: _stop('S4', 'Delta'),
        seconds: 450, // 3 hops x 150s
        waitSeconds: 300,
        routeId: 'R1',
        stations: [
          _stop('S1', 'Alpha'),
          _stop('S2', 'Bravo'),
          _stop('S3', 'Charlie'),
          _stop('S4', 'Delta'),
        ],
      ),
    ],
  );
}

JourneyPlan _interchangePlan() {
  final departure = DateTime(2026, 1, 1, 8);
  return JourneyPlan(
    origin: _stop('S1', 'Alpha'),
    destination: _stop('X3', 'South Gate'),
    departureAt: departure,
    expectedArrivalAt: departure,
    expectedTravelSeconds: 1100,
    interchangeCount: 1,
    interchangeStopIds: const ['S2'],
    walkingDistanceM: 100,
    remainingStations: const [],
    legs: [
      JourneyLeg(
        kind: 'ride',
        board: _stop('S1', 'Alpha'),
        alight: _stop('S2', 'Bravo'),
        seconds: 150,
        waitSeconds: 300,
        routeId: 'R1',
        stations: [_stop('S1', 'Alpha'), _stop('S2', 'Bravo')],
      ),
      JourneyLeg(
        kind: 'walk',
        board: _stop('S2', 'Bravo'),
        alight: _stop('X2', 'Bravo North'),
        seconds: 200,
        distanceM: 100,
      ),
      JourneyLeg(
        kind: 'ride',
        board: _stop('X2', 'Bravo North'),
        alight: _stop('X3', 'South Gate'),
        seconds: 150,
        waitSeconds: 300,
        routeId: 'B1',
        stations: [_stop('X2', 'Bravo North'), _stop('X3', 'South Gate')],
      ),
    ],
  );
}

void main() {
  group('single-line timetable', () {
    final startedAt = DateTime(2026, 1, 1, 9);
    final timetable = JourneyTimetable.fromPlan(_singleLinePlan(), startedAt: startedAt);

    test('distributes ride time evenly and adds the boarding wait once', () {
      expect(timetable.stops, hasLength(3));
      expect(timetable.stops[0].stopId, 'S2');
      expect(timetable.stops[0].scheduledAt, startedAt.add(const Duration(seconds: 450)));
      expect(timetable.stops[1].scheduledAt, startedAt.add(const Duration(seconds: 600)));
      expect(timetable.stops[2].stopId, 'S4');
      expect(timetable.stops[2].scheduledAt, startedAt.add(const Duration(seconds: 750)));
      expect(timetable.estimatedArrivalAt, startedAt.add(const Duration(seconds: 750)));
    });

    test('no interchange boundary on a single-line journey', () {
      expect(timetable.stops.every((s) => !s.isInterchangeBoundary), isTrue);
    });

    test('at() before departure: nothing passed yet', () {
      final snapshot = timetable.at(startedAt);
      expect(snapshot.current, isNull);
      expect(snapshot.next?.stopId, 'S2');
      expect(snapshot.remainingCount, 3);
      expect(snapshot.arrived, isFalse);
    });

    test('at() mid-journey: one stop passed', () {
      final snapshot = timetable.at(startedAt.add(const Duration(seconds: 500)));
      expect(snapshot.current?.stopId, 'S2');
      expect(snapshot.next?.stopId, 'S3');
      expect(snapshot.remainingCount, 2);
    });

    test('at() after arrival', () {
      final snapshot = timetable.at(startedAt.add(const Duration(seconds: 900)));
      expect(snapshot.current?.stopId, 'S4');
      expect(snapshot.next, isNull);
      expect(snapshot.remainingCount, 0);
      expect(snapshot.arrived, isTrue);
      expect(snapshot.etaToDestination, Duration.zero);
    });
  });

  group('interchange timetable', () {
    final startedAt = DateTime(2026, 1, 1, 9);
    final timetable = JourneyTimetable.fromPlan(_interchangePlan(), startedAt: startedAt);

    test('walking legs advance the clock without producing a stop', () {
      expect(timetable.stops.map((s) => s.stopId), ['S2', 'X3']);
    });

    test('the alight point of a non-final leg is flagged as an interchange', () {
      expect(timetable.stops[0].isInterchangeBoundary, isTrue);
      expect(timetable.stops[1].isInterchangeBoundary, isFalse);
    });

    test('timing accounts for both boarding waits and the walk', () {
      // leg0: 300 wait + 150 ride = 450
      expect(timetable.stops[0].scheduledAt, startedAt.add(const Duration(seconds: 450)));
      // + 200 walk + 300 wait + 150 ride = 1100
      expect(timetable.stops[1].scheduledAt, startedAt.add(const Duration(seconds: 1100)));
      expect(timetable.estimatedArrivalAt, startedAt.add(const Duration(seconds: 1100)));
    });

    test('at() between the interchange and the destination', () {
      final snapshot = timetable.at(startedAt.add(const Duration(seconds: 700)));
      expect(snapshot.current?.stopId, 'S2');
      expect(snapshot.next?.stopId, 'X3');
      expect(snapshot.remainingCount, 1);
    });
  });

  test('anchoring to a later startedAt shifts every stop by the same amount', () {
    final early = JourneyTimetable.fromPlan(_singleLinePlan(), startedAt: DateTime(2026, 1, 1, 9));
    final late = JourneyTimetable.fromPlan(
      _singleLinePlan(),
      startedAt: DateTime(2026, 1, 1, 9, 10),
    );
    for (var i = 0; i < early.stops.length; i++) {
      expect(
        late.stops[i].scheduledAt.difference(early.stops[i].scheduledAt),
        const Duration(minutes: 10),
      );
    }
  });
}
