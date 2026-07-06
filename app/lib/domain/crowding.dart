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

/// Why the recommended coach was picked — straight from the recommendation
/// endpoint's own per-coach `reasons` list (e.g. "typically less crowded",
/// "stops nearest to a destination exit"), never an invented caption.
List<String> recommendedCoachReasons(Map<String, dynamic>? coach) {
  final recommended = coach?['recommended_coach'];
  final coaches = coach?['coaches'] as List<dynamic>?;
  final match = coaches
      ?.whereType<Map<String, dynamic>>()
      .where((c) => c['coach_index'] == recommended)
      .firstOrNull;
  final reasons = match?['reasons'] as List<dynamic>?;
  return reasons?.map((r) => '$r').toList(growable: false) ?? const [];
}

/// Whether the crowd figures behind that recommendation are observed,
/// modelled, or just a neutral prior — the same honesty label the backend
/// already computes (`CoachRecommendation.crowd_source`), surfaced instead
/// of silently presenting every crowd estimate the same way.
String? crowdSource(Map<String, dynamic>? coach) => coach?['crowd_source'] as String?;
