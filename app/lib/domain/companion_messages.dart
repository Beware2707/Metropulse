/// The category of a proactive companion message, so the UI can pick an icon
/// and tone without parsing the text itself.
enum CompanionMessageKind { arrived, arriving, interchange, boarding, nextStation }

/// One line of proactive guidance shown at the top of Journey Mode.
/// Pure Dart (no Flutter import) — immutable by construction: final fields,
/// const constructor.
class CompanionMessage {
  const CompanionMessage({required this.kind, required this.text});

  final CompanionMessageKind kind;
  final String text;

  @override
  bool operator ==(Object other) =>
      other is CompanionMessage && other.kind == kind && other.text == text;

  @override
  int get hashCode => Object.hash(kind, text);

  @override
  String toString() => 'CompanionMessage($kind, $text)';
}

/// Builds the single most relevant proactive line for the current journey
/// state, in priority order (arrival beats everything; then the imminent
/// interchange/destination; then routine boarding/riding guidance).
///
/// Returns null when there is nothing new worth proactively saying (e.g. mid
/// ride, well before the next event) — callers should keep showing the last
/// non-null message rather than blanking the banner.
///
/// Honesty note: [platformHint] is the trip's direction/headsign (e.g.
/// "Towards Rajiv Chowk"), not a literal platform number — DMRC's GTFS feed
/// does not carry platform numbers, so this function never invents one.
CompanionMessage? buildCompanionMessage({
  required bool arrived,
  required bool arrivingSoon,
  String? exitName,
  required bool approachingInterchange,
  String? interchangeStationName,
  required bool justBoarded,
  int? recommendedCoach,
  String? platformHint,
  String? nextStationName,
}) {
  if (arrived) {
    return const CompanionMessage(kind: CompanionMessageKind.arrived, text: "You've made it!");
  }
  if (arrivingSoon) {
    final text = exitName == null
        ? 'Almost there — this is your stop.'
        : 'Almost there — head out via $exitName.';
    return CompanionMessage(kind: CompanionMessageKind.arriving, text: text);
  }
  if (approachingInterchange && interchangeStationName != null) {
    return CompanionMessage(
      kind: CompanionMessageKind.interchange,
      text: 'Time to change trains at $interchangeStationName.',
    );
  }
  if (justBoarded && recommendedCoach != null) {
    final platform = platformHint == null ? '' : ' — platform for $platformHint';
    return CompanionMessage(
      kind: CompanionMessageKind.boarding,
      text: 'Hop on Coach ${recommendedCoach + 1}$platform.',
    );
  }
  if (nextStationName != null) {
    return CompanionMessage(
      kind: CompanionMessageKind.nextStation,
      text: 'Next up: $nextStationName.',
    );
  }
  return null;
}
