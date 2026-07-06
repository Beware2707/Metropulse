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

/// Real Delhi Metro line names keyed by the line code embedded in GTFS
/// `route_long_name`/`route_short_name` (e.g. "ORANGE/AIRPORT_New Delhi to
/// Dwarka Sector - 21", "O_DN") -- mirrors the code list `routeColor` in
/// theme.dart matches against, so the name and colour shown for a line are
/// always consistent with each other.
const Map<String, String> _lineNames = {
  'RED': 'Red Line',
  'YELLOW': 'Yellow Line',
  'BLUE': 'Blue Line',
  'GREEN': 'Green Line',
  'VIOLET': 'Violet Line',
  'PINK': 'Pink Line',
  'MAGENTA': 'Magenta Line',
  'ORANGE': 'Airport Express Line',
  'AIRPORT': 'Airport Express Line',
  'AQUA': 'Aqua Line',
  'GRAY': 'Grey Line',
  'GREY': 'Grey Line',
  'RAPID': 'Rapid Metro',
};

/// A real line name from a raw GTFS route name. DMRC's static feed crams a
/// line code and the full origin-to-destination description into one field
/// with an underscore (e.g. "ORANGE/AIRPORT_New Delhi to Dwarka Sector -
/// 21"), so the raw value is never fit to show or read aloud as-is.
String cleanLineName(String? raw) {
  if (raw == null || raw.isEmpty) return 'Unknown line';
  final upper = raw.toUpperCase();
  for (final entry in _lineNames.entries) {
    if (upper.contains(entry.key)) return entry.value;
  }
  return raw;
}

/// The "Origin to Destination" half of a raw route name, e.g. "New Delhi to
/// Dwarka Sector - 21" from "ORANGE/AIRPORT_New Delhi to Dwarka Sector -
/// 21". Null when the raw value doesn't follow that convention, so callers
/// can omit a second line rather than show a raw duplicate.
String? routeDescription(String? raw) {
  if (raw == null) return null;
  final index = raw.indexOf('_');
  if (index == -1 || index == raw.length - 1) return null;
  return raw.substring(index + 1).replaceAll(RegExp(r'\s+'), ' ').trim();
}
