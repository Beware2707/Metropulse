import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/journey_progress.dart';
import 'package:metropulse_app/domain/journey_timetable.dart';
import 'package:metropulse_app/domain/models/eta.dart';
import 'package:metropulse_app/domain/models/journey.dart';
import 'package:metropulse_app/domain/models/train.dart';

Vehicle _vehicle() =>
    Vehicle(vehicleId: 'v1', latitude: 28.6, longitude: 77.0, timestamp: DateTime(2026, 1, 1));

Train _train({
  StationRef? current,
  StationRef? next,
  List<StationRef> remaining = const [],
  bool stale = false,
}) {
  return Train(
    vehicle: _vehicle(),
    resolved: true,
    isStale: stale,
    currentStation: current,
    nextStation: next,
    remainingStations: remaining,
  );
}

void main() {
  group('remainingToDestination', () {
    test('finds the 1-based position of the destination', () {
      expect(remainingToDestination(['S3', 'S4'], 'S3'), 1);
      expect(remainingToDestination(['S3', 'S4'], 'S4'), 2);
    });

    test('0 when nothing remains, null when the destination is not on this run', () {
      expect(remainingToDestination([], 'S4'), 0);
      expect(remainingToDestination(['X2', 'X3'], 'S4'), isNull);
    });
  });

  group('fromLiveTrain', () {
    test('mid-ride snapshot reports current/next/remaining/fraction', () {
      final train = _train(
        current: const StationRef(stopId: 'S2', name: 'Bravo', sequence: 2),
        next: const StationRef(stopId: 'S3', name: 'Charlie', sequence: 3),
        remaining: const [
          StationRef(stopId: 'S3', name: 'Charlie', sequence: 3),
          StationRef(stopId: 'S4', name: 'Delta', sequence: 4),
        ],
      );
      final snapshot = fromLiveTrain(
        train: train,
        destinationStopId: 'S4',
        interchangeStopIds: const {},
        totalStations: 4,
      );
      expect(snapshot.source, JourneyProgressSource.liveVehicle);
      expect(snapshot.currentStationName, 'Bravo');
      expect(snapshot.nextStationName, 'Charlie');
      expect(snapshot.remainingStations, 2);
      expect(snapshot.fractionComplete, closeTo(0.5, 1e-9));
      expect(snapshot.arrivingSoon, isFalse);
      expect(snapshot.arrived, isFalse);
      expect(snapshot.justBoarded, isFalse);
    });

    test('just boarded when nothing has been passed yet', () {
      final train = _train(
        next: const StationRef(stopId: 'S2', name: 'Bravo', sequence: 2),
        remaining: const [
          StationRef(stopId: 'S2', name: 'Bravo', sequence: 2),
          StationRef(stopId: 'S3', name: 'Charlie', sequence: 3),
          StationRef(stopId: 'S4', name: 'Delta', sequence: 4),
        ],
      );
      final snapshot = fromLiveTrain(
        train: train,
        destinationStopId: 'S4',
        interchangeStopIds: const {},
        totalStations: 3,
      );
      expect(snapshot.justBoarded, isTrue);
      expect(snapshot.fractionComplete, 0.0);
    });

    test('arriving soon when the destination is the very next station', () {
      final train = _train(
        next: const StationRef(stopId: 'S4', name: 'Delta', sequence: 4),
        remaining: const [StationRef(stopId: 'S4', name: 'Delta', sequence: 4)],
      );
      final snapshot = fromLiveTrain(
        train: train,
        destinationStopId: 'S4',
        interchangeStopIds: const {},
        totalStations: 4,
      );
      expect(snapshot.arrivingSoon, isTrue);
      expect(snapshot.arrived, isFalse);
    });

    test('arrived when nothing remains', () {
      final train = _train(current: const StationRef(stopId: 'S4', name: 'Delta', sequence: 4));
      final snapshot = fromLiveTrain(
        train: train,
        destinationStopId: 'S4',
        interchangeStopIds: const {},
        totalStations: 4,
      );
      expect(snapshot.arrived, isTrue);
      expect(snapshot.remainingStations, 0);
    });

    test('destination absent from the current run is unknown, not zero', () {
      final train = _train(
        next: const StationRef(stopId: 'X2', name: 'Bravo North', sequence: 2),
        remaining: const [StationRef(stopId: 'X2', name: 'Bravo North', sequence: 2)],
      );
      final snapshot = fromLiveTrain(
        train: train,
        destinationStopId: 'X3',
        interchangeStopIds: const {},
        totalStations: 2,
      );
      expect(snapshot.remainingStations, isNull);
      expect(snapshot.arrived, isFalse);
      expect(snapshot.arrivingSoon, isFalse);
      expect(snapshot.fractionComplete, isNull);
    });

    test('flags an approaching interchange by the next station id', () {
      final train = _train(
        next: const StationRef(stopId: 'S2', name: 'Bravo', sequence: 2),
        remaining: const [StationRef(stopId: 'S2', name: 'Bravo', sequence: 2)],
      );
      final snapshot = fromLiveTrain(
        train: train,
        destinationStopId: 'X3',
        interchangeStopIds: const {'S2'},
        totalStations: 2,
      );
      expect(snapshot.approachingInterchange, isTrue);
      expect(snapshot.interchangeStationName, 'Bravo');
    });

    test('carries the ETA and delay for the destination station specifically', () {
      final train = _train(
        next: const StationRef(stopId: 'S4', name: 'Delta', sequence: 4),
        remaining: const [StationRef(stopId: 'S4', name: 'Delta', sequence: 4)],
      );
      final eta = VehicleEta(
        vehicleId: 'v1',
        tripId: 'T1',
        computedAt: DateTime(2026, 1, 1),
        confidence: 'high',
        delaySeconds: 90,
        stations: [
          StationEta(
            stopId: 'S3',
            stopName: 'Charlie',
            sequence: 3,
            distanceRemainingM: 50,
            etaSeconds: 20,
            etaTime: DateTime(2026, 1, 1, 8, 0, 20),
          ),
          StationEta(
            stopId: 'S4',
            stopName: 'Delta',
            sequence: 4,
            distanceRemainingM: 100,
            etaSeconds: 60,
            etaTime: DateTime(2026, 1, 1, 8, 1),
          ),
        ],
      );
      final snapshot = fromLiveTrain(
        train: train,
        destinationStopId: 'S4',
        interchangeStopIds: const {},
        totalStations: 4,
        eta: eta,
      );
      expect(snapshot.delaySeconds, 90);
      expect(snapshot.etaToDestination, const Duration(seconds: 60));
    });
  });

  group('fromTimetable', () {
    JourneyTimetable buildTimetable() {
      final departure = DateTime(2026, 1, 1, 8);
      final plan = JourneyPlan(
        origin: const JourneyStop(stopId: 'S1', name: 'Alpha'),
        destination: const JourneyStop(stopId: 'S4', name: 'Delta'),
        departureAt: departure,
        expectedArrivalAt: departure,
        expectedTravelSeconds: 750,
        interchangeCount: 0,
        interchangeStopIds: const [],
        walkingDistanceM: 0,
        remainingStations: const [],
        legs: [
          const JourneyLeg(
            kind: 'ride',
            board: JourneyStop(stopId: 'S1', name: 'Alpha'),
            alight: JourneyStop(stopId: 'S4', name: 'Delta'),
            seconds: 450,
            waitSeconds: 300,
            stations: [
              JourneyStop(stopId: 'S1', name: 'Alpha'),
              JourneyStop(stopId: 'S2', name: 'Bravo'),
              JourneyStop(stopId: 'S3', name: 'Charlie'),
              JourneyStop(stopId: 'S4', name: 'Delta'),
            ],
          ),
        ],
      );
      return JourneyTimetable.fromPlan(plan, startedAt: departure);
    }

    test('reflects the simulated position and never reports a delay', () {
      final timetable = buildTimetable();
      final snapshot = fromTimetable(
        timetable,
        timetable.startedAt.add(const Duration(seconds: 500)),
        interchangeStopIds: const {},
      );
      expect(snapshot.source, JourneyProgressSource.timetableEstimate);
      expect(snapshot.currentStationName, 'Bravo');
      expect(snapshot.nextStationName, 'Charlie');
      expect(snapshot.remainingStations, 2);
      expect(snapshot.delaySeconds, isNull);
    });

    test('reports arrived and zero ETA once past the destination', () {
      final timetable = buildTimetable();
      final snapshot = fromTimetable(
        timetable,
        timetable.estimatedArrivalAt.add(const Duration(minutes: 5)),
        interchangeStopIds: const {},
      );
      expect(snapshot.arrived, isTrue);
      expect(snapshot.etaToDestination, Duration.zero);
      expect(snapshot.fractionComplete, 1.0);
    });

    test('justBoarded is true before the first stop is reached', () {
      final timetable = buildTimetable();
      final snapshot = fromTimetable(timetable, timetable.startedAt, interchangeStopIds: const {});
      expect(snapshot.justBoarded, isTrue);
      expect(snapshot.fractionComplete, 0.0);
    });
  });
}
