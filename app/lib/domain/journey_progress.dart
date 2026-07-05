/// Pure progress math for Journey Mode's live indicator.
class JourneyProgress {
  const JourneyProgress({
    required this.totalStations,
    required this.remainingToDestination,
  });

  /// Stations from boarding to destination, boarding station excluded.
  final int totalStations;

  /// Stations still ahead including the destination; null while unknown
  /// (e.g. the tracked train is on an earlier leg of an interchange trip).
  final int? remainingToDestination;

  /// 0.0 (just boarded) .. 1.0 (arrived); null when progress is unknowable.
  double? get fraction {
    final remaining = remainingToDestination;
    if (remaining == null || totalStations <= 0) return null;
    final done = totalStations - remaining;
    return (done / totalStations).clamp(0.0, 1.0);
  }

  /// True when the destination is the very next station.
  bool get arrivingSoon => remainingToDestination == 1;

  String get label {
    final remaining = remainingToDestination;
    if (remaining == null) return '–';
    final done = (totalStations - remaining).clamp(0, totalStations);
    return '$done of $totalStations stations';
  }
}

/// Remaining-to-destination from a live train's remaining-station list.
///
/// Returns the 1-based position of [destinationStopId] within [remaining]
/// (so "next station is the destination" == 1), 0 when nothing remains, and
/// null when the destination isn't on this train's current run.
int? remainingToDestination(
  List<String> remainingStopIds,
  String destinationStopId,
) {
  if (remainingStopIds.isEmpty) return 0;
  final index = remainingStopIds.indexOf(destinationStopId);
  return index >= 0 ? index + 1 : null;
}
