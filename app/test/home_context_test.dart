import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/home_context.dart';

void main() {
  group('dayPartFor', () {
    test('buckets hours the same way the app has always greeted', () {
      expect(dayPartFor(DateTime(2026, 1, 1, 3, 0)), DayPart.lateNight);
      expect(dayPartFor(DateTime(2026, 1, 1, 8, 0)), DayPart.morning);
      expect(dayPartFor(DateTime(2026, 1, 1, 14, 0)), DayPart.afternoon);
      expect(dayPartFor(DateTime(2026, 1, 1, 19, 0)), DayPart.evening);
      expect(dayPartFor(DateTime(2026, 1, 1, 22, 0)), DayPart.night);
    });
  });

  group('emojiForDayPart / greetingForDayPart', () {
    test('every day part has a day/night-appropriate emoji and greeting', () {
      expect(emojiForDayPart(DayPart.morning), '🌅');
      expect(emojiForDayPart(DayPart.afternoon), '☀️');
      expect(emojiForDayPart(DayPart.evening), '🌇');
      expect(emojiForDayPart(DayPart.night), '🌙');
      expect(emojiForDayPart(DayPart.lateNight), '🌙');
      expect(greetingForDayPart(DayPart.morning), 'Good morning!');
      expect(greetingForDayPart(DayPart.lateNight), 'Still up?');
    });
  });

  group('resolveHomeContextMessage', () {
    test('a learned commute departing soon wins: "Monday, 8:00 AM" example', () {
      final message = resolveHomeContextMessage(
        now: DateTime(2026, 1, 5, 7, 48), // a Monday
        leaveInSeconds: 12 * 60,
        commuteDestinationName: 'Cyber City',
      );
      expect(message, 'Leave in 12 minutes to reach Cyber City on time.');
    });

    test('singular minute reads naturally', () {
      final message = resolveHomeContextMessage(
        now: DateTime(2026, 1, 5, 7, 59),
        leaveInSeconds: 61,
        commuteDestinationName: 'Cyber City',
      );
      expect(message, 'Leave in 1 minute to reach Cyber City on time.');
    });

    test('under a minute reads as "leave now"', () {
      final message = resolveHomeContextMessage(
        now: DateTime(2026, 1, 5, 8, 0),
        leaveInSeconds: 20,
        commuteDestinationName: 'Cyber City',
      );
      expect(message, 'Leave now to reach Cyber City on time.');
    });

    test('a commute more than an hour away does not pre-empt the day', () {
      final message = resolveHomeContextMessage(
        now: DateTime(2026, 1, 5, 5, 0),
        leaveInSeconds: 3 * 3600,
        commuteDestinationName: 'Cyber City',
      );
      expect(message, isNot(contains('Leave')));
    });

    test('late at night, an imminent last train wins over the explore prompt', () {
      final message = resolveHomeContextMessage(
        now: DateTime(2026, 1, 5, 23, 10),
        lastTrainInSeconds: 18 * 60,
      );
      expect(message, 'Last train on your route departs in 18 minutes.');
    });

    test('a distant last train does not fire early in the evening', () {
      final message = resolveHomeContextMessage(
        now: DateTime(2026, 1, 5, 19, 0),
        lastTrainInSeconds: 18 * 60,
      );
      expect(message, isNot(contains('Last train')));
    });

    test('weekend afternoon with nothing learned falls back to the explore prompt', () {
      final message = resolveHomeContextMessage(now: DateTime(2026, 1, 10, 14, 30)); // a Saturday
      expect(message, 'Planning a trip? Search a station or explore nearby places.');
    });

    test('a commute departure wins over a simultaneously-imminent last train', () {
      final message = resolveHomeContextMessage(
        now: DateTime(2026, 1, 5, 23, 50),
        leaveInSeconds: 5 * 60,
        commuteDestinationName: 'Night Market',
        lastTrainInSeconds: 10 * 60,
      );
      expect(message, contains('Leave in 5 minutes'));
    });
  });
}
