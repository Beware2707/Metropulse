// Counting station stops with no radio, and vetoing the impossible ones.
//
// This is the only source that works in a tunnel, so it carries the most risk:
// a miscount does not degrade gracefully, it puts a rider at the wrong
// platform. The tests below are mostly about refusing to count.
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/motion_stop_counter.dart';

final _start = DateTime(2026, 8, 9, 9);

/// Feed [seconds] of samples at 1 Hz with the given variation.
DateTime _feed(
  MotionStopCounter counter,
  DateTime from,
  int seconds, {
  required bool moving,
}) {
  var t = from;
  for (var i = 0; i < seconds; i++) {
    // A moving train vibrates; a stopped one barely varies.
    final magnitude = moving ? (i.isEven ? 9.0 : 10.6) : 9.81;
    counter.add(MotionSample(magnitude: magnitude, at: t));
    t = t.add(const Duration(seconds: 1));
  }
  return t;
}

void main() {
  group('what counts as a station stop', () {
    test('a long dwell after a real run counts', () {
      final counter = MotionStopCounter();
      var t = _feed(counter, _start, 90, moving: true);
      t = _feed(counter, t, 25, moving: false);
      expect(counter.stops, 1);
    });

    test('a brief jolt does not', () {
      // Doors, a rough joint, a signal check — shorter than any platform stop.
      final counter = MotionStopCounter();
      var t = _feed(counter, _start, 90, moving: true);
      t = _feed(counter, t, 5, moving: false);
      expect(counter.stops, 0);
    });

    test('a hold too soon after departing does not count', () {
      // THE failure this guard exists for: a train stopped mid-tunnel looks
      // exactly like a platform to an accelerometer. Distance is what we
      // cannot measure, so time since the last departure stands in for it.
      final counter = MotionStopCounter();
      var t = _feed(counter, _start, 90, moving: true);
      t = _feed(counter, t, 25, moving: false); // station 1
      t = _feed(counter, t, 20, moving: true); // only 20 s of running
      t = _feed(counter, t, 40, moving: false); // held in the tunnel

      expect(counter.stops, 1, reason: 'the tunnel hold is not a station');
    });

    test('two genuine stations both count', () {
      final counter = MotionStopCounter();
      var t = _feed(counter, _start, 90, moving: true);
      t = _feed(counter, t, 25, moving: false);
      t = _feed(counter, t, 120, moving: true);
      t = _feed(counter, t, 25, moving: false);
      expect(counter.stops, 2);
    });

    test('confidence decays as unconfirmed stops accumulate', () {
      final counter = MotionStopCounter();
      var t = _feed(counter, _start, 90, moving: true);
      final first = counter.add(MotionSample(magnitude: 9.81, at: t));
      t = _feed(counter, t, 25, moving: false);
      t = _feed(counter, t, 120, moving: true);
      final later = _lastOf(counter, t, 25);

      expect(later.confidence, lessThan(first.confidence),
          reason: 'dead reckoning accumulates error; the label must show it');
    });

    test('a confirmed position resets both count and confidence', () {
      final counter = MotionStopCounter();
      var t = _feed(counter, _start, 90, moving: true);
      t = _feed(counter, t, 25, moving: false);

      counter.confirmPosition(stopsSoFar: 5);
      final after = counter.add(MotionSample(magnitude: 9.81, at: t));

      expect(after.stops, 5);
      expect(after.confidence, 1.0);
    });
  });

  group('the timetable vetoes impossible counts', () {
    // Fastest possible arrival at stations 1..4 from the origin.
    final fastest = [
      const Duration(minutes: 2),
      const Duration(minutes: 4),
      const Duration(minutes: 6),
      const Duration(minutes: 8),
    ];

    test('a count the elapsed time cannot support is corrected down', () {
      // Three stops claimed four minutes in. The fastest run reaches only two
      // by then, so the third cannot have happened — that is a fact about
      // physics, not a preference between two estimates.
      final checked = MotionStopCounter.reconcile(
        counted: 3,
        elapsed: const Duration(minutes: 4),
        cumulativeFastestRun: fastest,
      );

      expect(checked.stops, 2);
      expect(checked.wasCorrected, isTrue);
    });

    test('a plausible count is left alone', () {
      final checked = MotionStopCounter.reconcile(
        counted: 2,
        elapsed: const Duration(minutes: 5),
        cumulativeFastestRun: fastest,
      );
      expect(checked.stops, 2);
      expect(checked.wasCorrected, isFalse);
    });

    test('a slow journey is NEVER revised upwards', () {
      // Twenty minutes in with one stop counted looks like a badly delayed
      // train — and looks identical to a missed dwell. Nothing in the timing
      // separates them, so revising up would risk putting the rider a station
      // ahead of where they are: the exact harm this feature prevents.
      final checked = MotionStopCounter.reconcile(
        counted: 1,
        elapsed: const Duration(minutes: 20),
        cumulativeFastestRun: fastest,
      );

      expect(checked.stops, 1);
      expect(checked.wasCorrected, isFalse);
    });

    test('before the first station could be reached, no count survives', () {
      final checked = MotionStopCounter.reconcile(
        counted: 2,
        elapsed: const Duration(seconds: 30),
        cumulativeFastestRun: fastest,
      );
      expect(checked.stops, 0);
      expect(checked.wasCorrected, isTrue);
    });

    test('an empty timetable vetoes everything rather than trusting blindly', () {
      final checked = MotionStopCounter.reconcile(
        counted: 3,
        elapsed: const Duration(minutes: 30),
        cumulativeFastestRun: const [],
      );
      expect(checked.stops, 0);
      expect(checked.wasCorrected, isTrue);
    });
  });
}

StopCount _lastOf(MotionStopCounter counter, DateTime from, int seconds) {
  var t = from;
  late StopCount last;
  for (var i = 0; i < seconds; i++) {
    last = counter.add(MotionSample(magnitude: 9.81, at: t));
    t = t.add(const Duration(seconds: 1));
  }
  return last;
}
