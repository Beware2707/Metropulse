import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/models/station.dart';
import 'package:metropulse_app/domain/nearby.dart';

const _stations = [
  Station(stopId: 'S1', name: 'Alpha', lat: 28.60, lon: 77.00),
  Station(stopId: 'S2', name: 'Bravo', lat: 28.60, lon: 77.01),
  Station(stopId: 'S3', name: 'Charlie', lat: 28.60, lon: 77.02),
  Station(stopId: 'S4', name: 'Delta', lat: 28.70, lon: 77.30),
];

void main() {
  test('haversine matches known distances', () {
    // One degree of latitude is ~111.2 km.
    expect(haversineMeters(28.0, 77.0, 29.0, 77.0), closeTo(111200, 1500));
    expect(haversineMeters(28.6, 77.0, 28.6, 77.0), 0);
  });

  test('nearestStations sorts by distance and caps the count', () {
    // Standing just east of Bravo.
    final nearby = nearestStations(_stations, 28.60, 77.011, count: 2);
    expect(nearby.map((n) => n.station.stopId), ['S2', 'S3']);
    expect(nearby.first.distanceM, lessThan(nearby.last.distanceM));
    expect(nearby.first.distanceM, closeTo(98, 10)); // ~0.001 deg lon
  });

  test('nearestStations tolerates fewer stations than requested', () {
    final nearby = nearestStations(_stations.take(1).toList(), 28.6, 77.0, count: 5);
    expect(nearby, hasLength(1));
  });
}
