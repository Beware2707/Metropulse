import 'package:intl/intl.dart';

final _timeFormat = DateFormat('h:mm a');

/// '8:43 AM' in the device's local timezone.
String clockTime(DateTime? time) =>
    time == null ? '–' : _timeFormat.format(time.toLocal());

/// '2 min', '32 min', '1 h 05 min' — commuter-friendly durations.
String minutesLabel(double? seconds) {
  if (seconds == null) return '–';
  final total = (seconds / 60).round();
  if (total < 1) return 'now';
  if (total < 60) return '$total min';
  final hours = total ~/ 60;
  final minutes = (total % 60).toString().padLeft(2, '0');
  return '$hours h $minutes min';
}

/// '350 m' / '1.2 km'.
String distanceLabel(double? meters) {
  if (meters == null) return '–';
  if (meters < 1000) return '${meters.round()} m';
  return '${(meters / 1000).toStringAsFixed(1)} km';
}

/// '1 stop' / '5 stops'.
String stopsLabel(int count) => '$count ${count == 1 ? 'stop' : 'stops'}';

/// Like [minutesLabel] but for a duration that already elapsed, where
/// "now" (correct for an ETA) would misread as "this took no time at all"
/// instead of "this was quick".
String elapsedLabel(double? seconds) {
  if (seconds == null) return '–';
  final total = (seconds / 60).round();
  if (total < 1) return 'under a minute';
  return minutesLabel(seconds);
}
