import 'models/journey.dart';

/// A DMRC-style distance-slab smart-card fare, clearly ESTIMATED.
///
/// DMRC does not publish a fare API and this project does not add one (the
/// backend's job is routing, not billing) — [estimatedDistanceKm] is derived
/// from the journey's real ride time at an assumed average commercial speed
/// (including dwell), which reliably places a trip in the correct fare slab
/// for the vast majority of real journeys. Callers must present this as an
/// estimate, never as the exact fare a gate will charge.
class FareEstimate {
  const FareEstimate({required this.rupees, required this.estimatedDistanceKm});

  final int rupees;
  final double estimatedDistanceKm;
}

/// Average Delhi Metro commercial speed (line-haul, dwell included), km/h.
/// Public operational figures place this in the low-to-mid 30s; 33 km/h is a
/// reasonable midpoint that keeps slab placement correct for typical trips.
const double kAssumedMetroSpeedKmh = 33.0;

/// DMRC smart-card fare slabs (rupees), upper-bound-inclusive, ascending.
/// Kept as a small ordered table so it is trivially updated if DMRC revises
/// fares — nothing else in this function needs to change.
const List<(double maxKm, int rupees)> _fareSlabs = [
  (2.0, 10),
  (5.0, 20),
  (12.0, 30),
  (21.0, 40),
  (32.0, 50),
];
const int _fareBeyondLastSlab = 60;

/// Estimates the smart-card fare for [plan] from its real, schedule-derived
/// ride time (walking legs contribute their real distance, not an estimate).
FareEstimate estimateFare(JourneyPlan plan) {
  final rideSeconds = plan.legs
      .where((leg) => leg.isRide)
      .fold<double>(0, (sum, leg) => sum + leg.seconds);
  final rideKm = rideSeconds / 3600.0 * kAssumedMetroSpeedKmh;
  final walkKm = plan.walkingDistanceM / 1000.0;
  final totalKm = rideKm + walkKm;
  return FareEstimate(rupees: _slabFare(totalKm), estimatedDistanceKm: totalKm);
}

int _slabFare(double km) {
  for (final (maxKm, rupees) in _fareSlabs) {
    if (km <= maxKm) return rupees;
  }
  return _fareBeyondLastSlab;
}
