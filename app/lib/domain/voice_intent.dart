/// The category of question the Voice Assistant recognises. Anything that
/// doesn't match one of these is [unknown] — the assistant explicitly
/// declines rather than guessing or chatting generically. Pure Dart, no
/// Flutter/provider imports: this is a deterministic classifier, not a
/// language model.
enum VoiceIntentKind {
  routeTo,
  whenToLeave,
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
  const VoiceIntent({required this.kind, required this.rawText, this.stationQuery});

  final VoiceIntentKind kind;
  final String rawText;
  final String? stationQuery;

  @override
  String toString() => 'VoiceIntent($kind, query: $stationQuery, raw: "$rawText")';
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
    RegExp(r'\b(when (should|do|can) i leave|what time should i leave|leave now|leave for)\b'),
    VoiceIntentKind.whenToLeave,
  ),
  (
    RegExp(r'\b(fare|ticket price|how much (does it|will it|to)|how much is)\b'),
    VoiceIntentKind.fareQuery,
  ),
  (
    RegExp(r'\b(how do i (get|reach)|how to reach|route to|way to|take me to|go to)\b'),
    VoiceIntentKind.routeTo,
  ),
];

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
