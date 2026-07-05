import 'dart:math' as math;

import 'models/station.dart';

/// A station with its straight-line distance from the user.
class NearbyStation {
  const NearbyStation({required this.station, required this.distanceM});

  final Station station;
  final double distanceM;
}

/// The [count] stations closest to (lat, lon), nearest first.
///
/// Pure function over the offline bundle so "nearby" works with no network —
/// only a location fix is needed.
List<NearbyStation> nearestStations(
  List<Station> stations,
  double lat,
  double lon, {
  int count = 3,
}) {
  final measured = [
    for (final station in stations)
      NearbyStation(
        station: station,
        distanceM: haversineMeters(lat, lon, station.lat, station.lon),
      ),
  ]..sort((a, b) => a.distanceM.compareTo(b.distanceM));
  return measured.take(count).toList(growable: false);
}

/// Great-circle distance in metres between two WGS84 coordinates.
double haversineMeters(double lat1, double lon1, double lat2, double lon2) {
  const earthRadius = 6371008.8;
  final phi1 = _rad(lat1);
  final phi2 = _rad(lat2);
  final dPhi = _rad(lat2 - lat1);
  final dLambda = _rad(lon2 - lon1);
  final a = math.pow(math.sin(dPhi / 2), 2) +
      math.cos(phi1) * math.cos(phi2) * math.pow(math.sin(dLambda / 2), 2);
  return 2 * earthRadius * math.asin(math.sqrt(a.toDouble()));
}

double _rad(double degrees) => degrees * math.pi / 180.0;
