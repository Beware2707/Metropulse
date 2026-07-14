// Pure timing logic for the "remind me before the last train" affordance —
// kept free of Flutter and plugin imports so it's unit-testable on its own.

/// The lead time, in minutes, a last-train reminder fires ahead of the
/// train's departure. Matches the backend reminder default.
const int lastTrainReminderLeadMinutes = 30;

/// When a last-train reminder should fire: [leadMinutes] before
/// [departureAt]. Returns null when that moment is already at or in the past
/// relative to [now] (the last train is too close, or already gone), so
/// callers can honestly disable scheduling instead of firing a useless alert
/// immediately.
DateTime? lastTrainReminderTime({
  required DateTime departureAt,
  required DateTime now,
  int leadMinutes = lastTrainReminderLeadMinutes,
}) {
  final fireAt = departureAt.subtract(Duration(minutes: leadMinutes));
  if (!fireAt.isAfter(now)) return null;
  return fireAt;
}
