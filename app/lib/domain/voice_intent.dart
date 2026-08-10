/// The category of question the Voice Assistant recognises. Anything that
/// doesn't match one of these is [unknown] — the assistant explicitly
/// declines rather than guessing or chatting generically. Pure Dart, no
/// Flutter/provider imports: this is a deterministic classifier, not a
/// language model.
enum VoiceIntentKind {
  routeTo,
  planJourney,
  whenToLeave,
  runningLate,
  whichCoach,
  nextStation,
  fareQuery,
  onTrack,
  unknown,
}

/// One parsed utterance: its recognised intent and, for [VoiceIntentKind.routeTo],
/// the free-text place name to resolve — resolution itself happens elsewhere
/// (the existing offline search index), this layer only classifies.
class VoiceIntent {
  const VoiceIntent({
    required this.kind,
    required this.rawText,
    this.stationQuery,
    this.originQuery,
  });

  final VoiceIntentKind kind;
  final String rawText;

  /// Where they want to go.
  final String? stationQuery;

  /// Where they are starting from, when they said so ("from Dwarka to Saket").
  ///
  /// Null means "use my Home station", which is what the assistant assumed for
  /// everyone until now — unhelpful for the very common case of planning a trip
  /// that does not start at home, and useless for anyone who has not set a Home
  /// station at all.
  final String? originQuery;

  @override
  String toString() => 'VoiceIntent($kind, from: $originQuery, to: $stationQuery, '
      'raw: "$rawText")';
}

// Ordered most-specific-first: the first matching pattern wins. Deliberately
// narrow and metro-specific — this is the enforcement point for "answer
// only metro-related questions".
final List<(RegExp, VoiceIntentKind)> _patterns = [
  (
    RegExp(r'\b(right way|right train|correct train|on track|going the right)\b'),
    VoiceIntentKind.onTrack,
  ),
  (RegExp(r'\b(next station|next stop|where am i)\b'), VoiceIntentKind.nextStation),
  (RegExp(r'\b(which coach|what coach|best coach|coach should i)\b'), VoiceIntentKind.whichCoach),
  (
    RegExp(r"\b(running late|i'?m late|behind schedule|late for (my|the) train)\b"),
    VoiceIntentKind.runningLate,
  ),
  (
    RegExp(r'\b(when (should|do|can) i leave|what time should i leave|leave now|leave for)\b'),
    VoiceIntentKind.whenToLeave,
  ),
  (
    RegExp(r'\b(fare|ticket price|how much (does it|will it|to)|how much is)\b'),
    VoiceIntentKind.fareQuery,
  ),
  // Route requests. Deliberately generous about phrasing: "best route FROM
  // Rajiv Chowk TO Saket" used to fall through to `unknown` because the only
  // route trigger was the literal "route to", so the single most natural way
  // to ask the question was the one way that failed.
  (
    RegExp(
      r'\b(how do i (get|reach|go)|how to (reach|get)|'
      r'(best|fastest|quickest|shortest) route|route (to|from)|'
      r'directions? (to|from)|way to|take me to|get me to|go to|'
      r'plan a (trip|journey|route) to|travel to)\b',
    ),
    VoiceIntentKind.routeTo,
  ),
  // Bare "set up a new journey" — no destination named, so this opens the
  // planner rather than guessing at a station. Checked AFTER routeTo so
  // "plan a trip to Saket" still resolves to a real route.
  (
    RegExp(
      r'\b((set ?up|start|create|begin|make|plan) (a |an |my )?(new )?'
      r'(journey|trip|route)|new journey|new trip)\b',
    ),
    VoiceIntentKind.planJourney,
  ),
];

/// "from X to Y" — the shape that carries BOTH endpoints.
///
/// Non-greedy on the origin so "from dwarka sector 10 to saket" splits at the
/// LAST plausible "to" rather than swallowing the destination; anchored to the
/// end so a trailing "to" cannot produce an empty destination.
final _fromToPattern = RegExp(r'\bfrom\s+(.+?)\s+to\s+(.+)$');

/// Classifies one recognised speech transcript. Never throws — an
/// unrecognised or off-topic utterance simply comes back [VoiceIntentKind.unknown].
VoiceIntent parseVoiceIntent(String transcript) {
  final normalized = transcript.trim().toLowerCase();
  if (normalized.isEmpty) {
    return VoiceIntent(kind: VoiceIntentKind.unknown, rawText: transcript);
  }
  for (final (pattern, kind) in _patterns) {
    final match = pattern.firstMatch(normalized);
    if (match == null) continue;
    if (kind == VoiceIntentKind.routeTo) {
      // "from X to Y" names both ends, and is read from the WHOLE utterance,
      // not just the tail: "what's the best route from A to B" puts "from" in
      // front of the trigger match in some phrasings and after it in others.
      final fromTo = _fromToPattern.firstMatch(normalized);
      if (fromTo != null) {
        final origin = _stripFillerWords(fromTo.group(1)!);
        final destination = _stripFillerWords(fromTo.group(2)!);
        if (origin.isNotEmpty && destination.isNotEmpty) {
          return VoiceIntent(
            kind: kind,
            rawText: transcript,
            originQuery: origin,
            stationQuery: destination,
          );
        }
      }
      final remainder = _stripFillerWords(normalized.substring(match.end));
      if (remainder.isEmpty) continue; // matched a trigger but named no place
      return VoiceIntent(kind: kind, rawText: transcript, stationQuery: remainder);
    }
    return VoiceIntent(kind: kind, rawText: transcript);
  }
  return VoiceIntent(kind: VoiceIntentKind.unknown, rawText: transcript);
}

String _stripFillerWords(String text) {
  final withoutPunctuation = text.trim().replaceAll(RegExp(r'[?.!,]+$'), '').trim();
  return withoutPunctuation.replaceFirst(RegExp(r'^(to|the|station)\s+'), '').trim();
}
