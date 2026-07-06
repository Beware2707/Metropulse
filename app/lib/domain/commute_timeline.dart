import 'journey_timetable.dart';
import 'models/commute_card.dart';
import 'models/journey.dart';

/// How urgently the rider needs to act, given the commute's normal leave-by
/// time and today's known route delay.
enum CommuteUrgency { onTime, leaveNow, actSoon, overdue }

/// The delay-aware headline shown above the Commute Timeline. Every input is
/// real: [CommuteCard.leaveBy] already bakes in the same walk-to-station
/// buffer shown everywhere else in the app, and the delay is the backend's
/// historical, route-and-hour-of-day estimate (`DelayPredictionService`) —
/// never a live per-vehicle feed, and always clamped to zero rather than
/// promising an early arrival.
class CommuteTimelineStatus {
  const CommuteTimelineStatus({
    required this.urgency,
    required this.headline,
    this.subline,
    this.reason,
    this.confidence,
  });

  final CommuteUrgency urgency;
  final String headline;
  final String? subline;

  /// A one-line, real cause for the urgency — e.g. "Blue Line is running
  /// about 12 min behind today" — never shown for [CommuteUrgency.onTime],
  /// and omitted (not guessed) whenever there's no route name to attribute
  /// the delay to.
  final String? reason;

  /// The delay estimate's own confidence (0..1, from `DelayEstimate`) — how
  /// much history that "running behind" figure rests on. Null whenever
  /// [reason] is null.
  final double? confidence;
}

/// The same "worth mentioning" cutoff Journey Mode's running-late banner
/// already uses (journey_mode_screen.dart), so the whole app agrees on what
/// counts as a delay worth surfacing.
const delayWorthMentioningSeconds = 120.0;

/// How much margin, after accounting for the delay, still reads as
/// comfortable rather than "cutting it close".
const comfortableMarginSeconds = 120.0;

/// Resolves the headline for right now. [leaveBy] must be a real, already
/// -computed commute-card time; callers should simply not show a timeline at
/// all when the card has no configured commute (i.e. `leaveBy == null`).
CommuteTimelineStatus resolveCommuteTimelineStatus({
  required DateTime now,
  required DateTime leaveBy,
  required double delaySeconds,
  String? routeLongName,
  double? delayConfidence,
}) {
  final delay = delaySeconds < 0 ? 0.0 : delaySeconds;
  if (delay < delayWorthMentioningSeconds) {
    return const CommuteTimelineStatus(urgency: CommuteUrgency.onTime, headline: 'Everything is on time.');
  }

  final slackSeconds = leaveBy.difference(now).inSeconds.toDouble();
  final netSeconds = slackSeconds - delay;

  if (netSeconds >= comfortableMarginSeconds) {
    return const CommuteTimelineStatus(urgency: CommuteUrgency.onTime, headline: 'Everything is on time.');
  }

  final delayMinutes = (delay / 60).round().clamp(1, 999);
  final reason = routeLongName == null ? null : '$routeLongName is running about $delayMinutes min behind today.';

  if (netSeconds >= -comfortableMarginSeconds) {
    return CommuteTimelineStatus(
      urgency: CommuteUrgency.leaveNow,
      headline: 'Leave now.',
      subline: "You'll still make it.",
      reason: reason,
      confidence: delayConfidence,
    );
  }
  if (slackSeconds > 0) {
    final leaveWithinMinutes = (slackSeconds / 60).ceil().clamp(1, 60);
    final lateByMinutes = (-netSeconds / 60).round().clamp(1, 999);
    return CommuteTimelineStatus(
      urgency: CommuteUrgency.actSoon,
      headline: 'Leave within $leaveWithinMinutes min.',
      subline: "Otherwise you'll arrive about $lateByMinutes min late.",
      reason: reason,
      confidence: delayConfidence,
    );
  }
  final lateByMinutes = (-netSeconds / 60).round().clamp(1, 999);
  return CommuteTimelineStatus(
    urgency: CommuteUrgency.overdue,
    headline: "You're already running late.",
    subline: 'Expect to arrive about $lateByMinutes min late.',
    reason: reason,
    confidence: delayConfidence,
  );
}

/// One row of the "Leave Home → Board → interchange(s) → Destination"
/// timeline.
class CommuteTimelineStep {
  const CommuteTimelineStep({required this.title, required this.time, this.isInterchange = false});

  final String title;
  final DateTime time;
  final bool isInterchange;
}

/// Builds today's commute timeline. The Leave-Home/Board/Destination anchor
/// times always come straight from [card] — the same numbers already shown
/// elsewhere on Home — never recomputed, so the two views can't disagree.
/// [plan]'s leg structure (which stops are interchange points, and each
/// leg's relative duration) is reused, via the same [JourneyTimetable]
/// simulation Journey Mode itself runs, purely to place interchange stops in
/// time; re-anchored at the train's already-known real departure ([
/// CommuteCard.nextDepartureAt]) rather than the plan's own (re-planned
/// "now") departure, so the first leg's own platform-wait isn't
/// double-counted on top of a moment already known exactly.
///
/// Returns an empty list — never a guessed one — when the card doesn't have
/// a full set of real anchor times yet.
List<CommuteTimelineStep> buildCommuteTimelineSteps({required CommuteCard card, required JourneyPlan? plan}) {
  final leaveBy = card.leaveBy;
  final boardAt = card.nextDepartureAt;
  final arriveAt = card.expectedArrivalAt;
  if (leaveBy == null || boardAt == null || arriveAt == null) return const [];

  final steps = <CommuteTimelineStep>[
    CommuteTimelineStep(title: 'Leave Home', time: leaveBy),
    CommuteTimelineStep(
      title: card.routeLongName == null ? 'Board your train' : 'Board ${card.routeLongName}',
      time: boardAt,
    ),
  ];

  if (plan != null && plan.legs.isNotEmpty) {
    final legs = [...plan.legs];
    legs[0] = legs[0].copyWith(waitSeconds: 0);
    final anchoredPlan = plan.copyWith(legs: legs);
    final timetable = JourneyTimetable.fromPlan(anchoredPlan, startedAt: boardAt);
    for (final stop in timetable.stops) {
      if (stop.isInterchangeBoundary) {
        steps.add(CommuteTimelineStep(title: stop.name, time: stop.scheduledAt, isInterchange: true));
      }
    }
  }

  steps.add(CommuteTimelineStep(title: card.destinationName, time: arriveAt));
  return steps;
}
