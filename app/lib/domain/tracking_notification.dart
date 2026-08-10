// What the ongoing notification says, as a pure function.
//
// This is the surface a rider actually reads — glanced at on a moving train,
// often one-handed, sometimes as the only reason they look up in time. It is
// also the one place where a wrong claim has a physical cost: standing up at
// the wrong platform.
//
// Kept out of the service so the WORDING can be tested without an Android
// device, a notification channel, or a running foreground process.

import 'journey_tracking.dart';

/// The two lines of an ongoing tracking notification.
class TrackingNotification {
  const TrackingNotification({required this.title, required this.body});

  final String title;
  final String body;
}

/// Build the notification for one tracking update.
///
/// The body always carries provenance. A rider deciding whether to stand up
/// deserves to know whether we can see them or are guessing from a timetable —
/// and the difference is invisible unless we say it.
TrackingNotification buildTrackingNotification(TrackingUpdate update) {
  if (update.nextStation == null) {
    return const TrackingNotification(
      title: 'Journey complete',
      body: 'Tap to finish and see your trip.',
    );
  }

  final remaining = update.stationsRemaining;
  final stops = remaining == 1 ? '1 stop away' : '$remaining stops away';

  // "Get off next" earns its urgency only when we can see how close it is.
  // From a timetable it would be a guess dressed as an instruction.
  final title = update.isFinalStation && update.isApproaching
      ? 'Get off next — ${update.nextStation!.name}'
      : update.headline;

  return TrackingNotification(
    title: title,
    body: '$stops · ${update.sourceLabel}',
  );
}
