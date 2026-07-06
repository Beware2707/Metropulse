/// Expected crowd for the "Entering the Station" moment: the same
/// occupancy-average thresholds as the backend's commute_card.py
/// (`_crowd_and_coach`) — computed client-side from a coach
/// recommendation's raw `coaches` list, already fetched at journey start,
/// so no extra request is needed to show it.
///
/// Returns `'low'`, `'moderate'`, or `'high'`; null (never `'unknown'`)
/// when there's nothing to average, so the UI can omit the row rather than
/// guess at a crowd level it has no evidence for.
String? expectedCrowding(List<dynamic>? coaches) {
  if (coaches == null || coaches.isEmpty) return null;
  final occupancies = [
    for (final c in coaches) ((c as Map<String, dynamic>)['occupancy'] as num).toDouble(),
  ];
  final average = occupancies.reduce((a, b) => a + b) / occupancies.length;
  if (average < 0.45) return 'low';
  if (average < 0.7) return 'moderate';
  return 'high';
}
