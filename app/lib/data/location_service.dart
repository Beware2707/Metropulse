import 'package:geolocator/geolocator.dart';

/// Outcome of a location request, explicit about why there's no fix.
sealed class LocationResult {
  const LocationResult();
}

class LocationFix extends LocationResult {
  const LocationFix(this.lat, this.lon);
  final double lat;
  final double lon;
}

class LocationDenied extends LocationResult {
  const LocationDenied({required this.permanently});
  final bool permanently;
}

class LocationUnavailable extends LocationResult {
  const LocationUnavailable();
}

/// Thin, mockable wrapper over geolocator.
class LocationService {
  const LocationService();

  Future<LocationResult> currentPosition() async {
    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        return const LocationUnavailable();
      }
      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.deniedForever) {
        return const LocationDenied(permanently: true);
      }
      if (permission == LocationPermission.denied) {
        return const LocationDenied(permanently: false);
      }
      // Low accuracy is plenty for "which station is near me" and is the
      // battery-friendly choice.
      final position = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.low,
        timeLimit: const Duration(seconds: 8),
      );
      return LocationFix(position.latitude, position.longitude);
    } on Exception {
      return const LocationUnavailable();
    }
  }
}
