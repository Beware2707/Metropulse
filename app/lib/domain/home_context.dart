/// The home screen's dynamic greeting: resolves whichever single fact is
/// both available and timely into one message, rather than a wall of cards
/// competing for attention. Pure and deterministic so it's unit-testable
/// without touching Riverpod, DateTime.now(), or the network.
library;

const _oneHourSeconds = 3600;
const _lateNightStartHour = 22;
const _lateNightEndHour = 5;

enum DayPart { lateNight, morning, afternoon, evening, night }

/// Buckets the hour of day the same way the app's existing greeting text
/// does (`_greeting()` in home_screen.dart) — this just adds an emoji and a
/// name to those same boundaries rather than inventing new ones.
DayPart dayPartFor(DateTime now) {
  final hour = now.hour;
  if (hour < _lateNightEndHour) return DayPart.lateNight;
  if (hour < 12) return DayPart.morning;
  if (hour < 17) return DayPart.afternoon;
  if (hour < 21) return DayPart.evening;
  return DayPart.night;
}

String emojiForDayPart(DayPart part) => switch (part) {
      DayPart.lateNight => '🌙',
      DayPart.morning => '🌅',
      DayPart.afternoon => '☀️',
      DayPart.evening => '🌇',
      DayPart.night => '🌙',
    };

String greetingForDayPart(DayPart part) => switch (part) {
      DayPart.lateNight => 'Still up?',
      DayPart.morning => 'Good morning!',
      DayPart.afternoon => 'Good afternoon.',
      DayPart.evening => 'Good evening.',
      DayPart.night => 'Good night.',
    };

/// The single most relevant thing to tell the user right now, in priority
/// order:
/// 1. A learned commute departure within the hour — "Leave in N minutes".
/// 2. Late at night, a last train on the user's route within the hour.
/// 3. Otherwise, a generic explore prompt (weekend, off-peak, or nothing
///    learned yet).
String resolveHomeContextMessage({
  required DateTime now,
  int? leaveInSeconds,
  String? commuteDestinationName,
  int? lastTrainInSeconds,
}) {
  if (leaveInSeconds != null && leaveInSeconds >= 0 && leaveInSeconds <= _oneHourSeconds) {
    final destination = commuteDestinationName == null || commuteDestinationName.isEmpty
        ? ''
        : ' to reach $commuteDestinationName on time';
    if (leaveInSeconds <= 30) return 'Leave now$destination.';
    final minutes = (leaveInSeconds / 60).round().clamp(1, 60);
    return 'Leave in $minutes minute${minutes == 1 ? '' : 's'}$destination.';
  }

  final isLateNight = now.hour >= _lateNightStartHour || now.hour < _lateNightEndHour;
  if (isLateNight && lastTrainInSeconds != null && lastTrainInSeconds >= 0 && lastTrainInSeconds <= _oneHourSeconds) {
    final minutes = (lastTrainInSeconds / 60).round().clamp(1, 60);
    return 'Last train on your route departs in $minutes minute${minutes == 1 ? '' : 's'}.';
  }

  return 'Planning a trip? Search a station or explore nearby places.';
}
