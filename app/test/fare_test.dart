import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/fare.dart';
import 'package:metropulse_app/domain/models/journey.dart';

JourneyStop _stop(String id) => JourneyStop(stopId: id, name: id);

JourneyLeg _ride(double seconds, {double waitSeconds = 0, int stopCount = 2}) {
  return JourneyLeg(
    kind: 'ride',
    board: _stop('A'),
    alight: _stop('B'),
    seconds: seconds,
    waitSeconds: waitSeconds,
    stations: [for (var i = 0; i < stopCount; i++) _stop('S$i')],
  );
}

JourneyLeg _walk(double meters, double seconds) {
  return JourneyLeg(
    kind: 'walk',
    board: _stop('A'),
    alight: _stop('B'),
    seconds: seconds,
    distanceM: meters,
  );
}

JourneyPlan _plan(List<JourneyLeg> legs, {double walkingDistanceM = 0}) {
  final now = DateTime(2026, 1, 1, 8);
  return JourneyPlan(
    origin: _stop('A'),
    destination: _stop('B'),
    departureAt: now,
    expectedArrivalAt: now,
    expectedTravelSeconds: 0,
    interchangeCount: 0,
    interchangeStopIds: const [],
    walkingDistanceM: walkingDistanceM,
    remainingStations: const [],
    legs: legs,
  );
}

void main() {
  test('short ride falls in the lowest fare slab', () {
    // ~600s at 33 km/h ≈ 5.5 km -> slab boundary just above 5 km.
    final plan = _plan([_ride(600)]);
    final fare = estimateFare(plan);
    expect(fare.estimatedDistanceKm, closeTo(5.5, 0.2));
    expect(fare.rupees, 30);
  });

  test('very short ride is the cheapest slab', () {
    final plan = _plan([_ride(150)]); // ~1.375 km
    final fare = estimateFare(plan);
    expect(fare.rupees, 10);
  });

  test('long ride hits the top slab', () {
    final plan = _plan([_ride(3600 * 2)]); // ~66 km
    final fare = estimateFare(plan);
    expect(fare.rupees, 60);
  });

  test('walking distance contributes to the estimate but wait time does not', () {
    final noWait = estimateFare(_plan([_ride(600, waitSeconds: 0)]));
    final withWait = estimateFare(_plan([_ride(600, waitSeconds: 600)]));
    expect(withWait.estimatedDistanceKm, noWait.estimatedDistanceKm);

    final withWalk = estimateFare(
      _plan([_ride(600)], walkingDistanceM: 1000),
    );
    expect(withWalk.estimatedDistanceKm, greaterThan(noWait.estimatedDistanceKm));
  });

  test('walk-only legs are ignored for ride-time distance but not overall', () {
    final plan = _plan([_walk(500, 400)], walkingDistanceM: 500);
    final fare = estimateFare(plan);
    expect(fare.estimatedDistanceKm, closeTo(0.5, 0.01));
    expect(fare.rupees, 10);
  });

  test('slab boundaries are inclusive at the upper edge', () {
    // Exactly 2.0 km worth of ride time.
    const seconds = 2.0 / kAssumedMetroSpeedKmh * 3600;
    final fare = estimateFare(_plan([_ride(seconds)]));
    expect(fare.rupees, 10);
  });
}
