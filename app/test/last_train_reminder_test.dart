// The last-train reminder's fire time is pure logic: [leadMinutes] before the
// train's departure, and null once that moment has passed (so the UI can be
// honest instead of firing a useless alert). These tests pin that behaviour
// without touching Flutter or the notifications plugin.
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/features/station/last_train_reminder.dart';

void main() {
  test('fires exactly lead-minutes before departure', () {
    final departure = DateTime(2026, 7, 14, 23, 30);
    final now = DateTime(2026, 7, 14, 22, 0);

    final fireAt = lastTrainReminderTime(departureAt: departure, now: now);

    expect(fireAt, DateTime(2026, 7, 14, 23, 0));
    expect(
      departure.difference(fireAt!).inMinutes,
      lastTrainReminderLeadMinutes,
    );
  });

  test('honours a custom lead time', () {
    final departure = DateTime(2026, 7, 14, 23, 30);
    final now = DateTime(2026, 7, 14, 22, 0);

    final fireAt =
        lastTrainReminderTime(departureAt: departure, now: now, leadMinutes: 45);

    expect(fireAt, DateTime(2026, 7, 14, 22, 45));
  });

  test('returns null when the last train is inside the lead window', () {
    final departure = DateTime(2026, 7, 14, 23, 30);
    // Only 20 minutes to spare — less than the 30-minute lead.
    final now = DateTime(2026, 7, 14, 23, 10);

    expect(lastTrainReminderTime(departureAt: departure, now: now), isNull);
  });

  test('returns null when the fire time is exactly now (no useless instant alert)', () {
    final departure = DateTime(2026, 7, 14, 23, 30);
    final now = DateTime(2026, 7, 14, 23, 0); // fireAt == now

    expect(lastTrainReminderTime(departureAt: departure, now: now), isNull);
  });

  test('returns null when the last train has already gone', () {
    final departure = DateTime(2026, 7, 14, 23, 30);
    final now = DateTime(2026, 7, 15, 0, 5);

    expect(lastTrainReminderTime(departureAt: departure, now: now), isNull);
  });
}
