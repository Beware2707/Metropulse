import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/journey_progress.dart';

void main() {
  test('remainingToDestination finds the 1-based position', () {
    expect(remainingToDestination(['S3', 'S4'], 'S3'), 1);
    expect(remainingToDestination(['S3', 'S4'], 'S4'), 2);
    expect(remainingToDestination([], 'S4'), 0);
    // Destination not on this run (e.g. before an interchange).
    expect(remainingToDestination(['X2', 'X3'], 'S4'), isNull);
  });

  test('fraction fills as stations are passed', () {
    const start = JourneyProgress(totalStations: 4, remainingToDestination: 4);
    const mid = JourneyProgress(totalStations: 4, remainingToDestination: 2);
    const done = JourneyProgress(totalStations: 4, remainingToDestination: 0);
    expect(start.fraction, 0.0);
    expect(mid.fraction, 0.5);
    expect(done.fraction, 1.0);
  });

  test('arrivingSoon fires exactly when the destination is next', () {
    expect(
      const JourneyProgress(totalStations: 4, remainingToDestination: 1)
          .arrivingSoon,
      isTrue,
    );
    expect(
      const JourneyProgress(totalStations: 4, remainingToDestination: 2)
          .arrivingSoon,
      isFalse,
    );
  });

  test('unknown progress renders safely', () {
    const unknown = JourneyProgress(totalStations: 4, remainingToDestination: null);
    expect(unknown.fraction, isNull);
    expect(unknown.label, '–');
    expect(unknown.arrivingSoon, isFalse);
  });

  test('labels count completed stations', () {
    const mid = JourneyProgress(totalStations: 11, remainingToDestination: 4);
    expect(mid.label, '7 of 11 stations');
  });
}
