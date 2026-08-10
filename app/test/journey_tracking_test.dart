// Tracking the rider from their own GPS, and the rules that keep it honest.
//
// The feature exists because schedule-derived progress drifts — a train held
// at a platform keeps advancing on paper, which is how people miss stops. The
// risk it introduces is the opposite: a bad fix that looks authoritative. So
// most of what is pinned here is refusal — when NOT to trust a position, and
// what to say instead.
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/journey_tracking.dart';

// A straight-ish stretch of the Blue Line, real coordinates, ~1-2 km apart.
const _rajivChowk = TrackedStation(
    stopId: '1', name: 'Rajiv Chowk', lat: 28.6328, lon: 77.2197, underground: true);
const _barakhamba = TrackedStation(
    stopId: '2', name: 'Barakhamba Road', lat: 28.6299, lon: 77.2255, underground: true);
const _mandiHouse = TrackedStation(
    stopId: '3', name: 'Mandi House', lat: 28.6256, lon: 77.2344, underground: true);
const _supremeCourt = TrackedStation(
    stopId: '4', name: 'Supreme Court', lat: 28.6197, lon: 77.2436);

List<TrackedStation> get _route =>
    [_rajivChowk, _barakhamba, _mandiHouse, _supremeCourt];

RiderFix _at(TrackedStation s, {double accuracy = 20, Duration age = Duration.zero}) =>
    RiderFix(
      lat: s.lat,
      lon: s.lon,
      accuracyMeters: accuracy,
      at: DateTime(2026, 8, 9, 12).subtract(age),
    );

final _now = DateTime(2026, 8, 9, 12);

void main() {
  _undergroundSources();

  group('a fix is only used when it is worth using', () {
    test('a wildly imprecise fix is refused, and we say so', () {
      final tracker = JourneyTracker(stations: _route);
      final update = tracker.update(
        fix: _at(_mandiHouse, accuracy: 500),
        now: _now,
      );

      expect(update.source, TrackingSource.schedule);
      expect(update.sourceLabel, contains('no GPS signal'));
      expect(update.metresToNext, isNull,
          reason: 'a distance from a refused fix would be invented precision');
    });

    test('a stale fix is refused — a metro train moves a long way in a minute',
        () {
      final tracker = JourneyTracker(stations: _route);
      final update = tracker.update(
        fix: _at(_mandiHouse, age: const Duration(minutes: 3)),
        now: _now,
      );
      expect(update.source, TrackingSource.schedule);
    });

    test('a fix from the future is refused rather than trusted', () {
      final tracker = JourneyTracker(stations: _route);
      final update = tracker.update(
        fix: _at(_mandiHouse, age: const Duration(minutes: -5)),
        now: _now,
      );
      expect(update.source, TrackingSource.schedule);
    });

    test('a good fix is used, and carries a real distance', () {
      final tracker = JourneyTracker(stations: _route);
      final update = tracker.update(fix: _at(_rajivChowk), now: _now);

      expect(update.source, TrackingSource.gps);
      expect(update.nextStation?.name, 'Barakhamba Road');
      expect(update.metresToNext, isNotNull);
      expect(update.sourceLabel, contains('From your location'));
    });
  });

  group('underground is expected, not an error', () {
    test('losing the fix falls back to the timetable and keeps going', () {
      final tracker = JourneyTracker(stations: _route);
      tracker.update(fix: _at(_barakhamba), now: _now); // reached #1 by GPS

      // Into the tunnel: no fix at all, timetable says we are at Mandi House.
      final update = tracker.update(fix: null, now: _now, scheduleIndex: 2);

      expect(update.source, TrackingSource.schedule);
      expect(update.nextStation?.name, 'Supreme Court');
      expect(update.sourceLabel, contains('no GPS signal'));
    });

    test('"get ready to alight" is never claimed without a distance', () {
      // The approach alert is a claim about proximity. The timetable cannot
      // support it, and guessing is exactly what this feature exists to avoid.
      final tracker = JourneyTracker(stations: _route);
      final update = tracker.update(fix: null, now: _now, scheduleIndex: 2);

      expect(update.nextStation?.name, 'Supreme Court');
      expect(update.isApproaching, isFalse);
      expect(update.metresToNext, isNull);
    });
  });

  group('progress never runs backwards', () {
    test('a stray fix cannot rewind the journey and re-announce a station', () {
      final tracker = JourneyTracker(stations: _route);
      tracker.update(fix: _at(_mandiHouse), now: _now);
      expect(tracker.reachedIndex, 2);

      // A bad fix that lands back at the origin — multipath, or a cached
      // position from before boarding. Progress must hold.
      final update = tracker.update(fix: _at(_rajivChowk), now: _now);

      expect(tracker.reachedIndex, 2, reason: 'must not rewind');
      expect(update.nextStation?.name, 'Supreme Court');
    });

    test('a lagging timetable cannot pull GPS progress backwards either', () {
      final tracker = JourneyTracker(stations: _route);
      tracker.update(fix: _at(_mandiHouse), now: _now);

      final update = tracker.update(fix: null, now: _now, scheduleIndex: 0);

      expect(tracker.reachedIndex, 2);
      expect(update.nextStation?.name, 'Supreme Court');
    });
  });

  group('being nearest is not being there', () {
    test('mid-way between two stations does not count as reaching either', () {
      final tracker = JourneyTracker(stations: _route);
      // Halfway between Barakhamba and Mandi House — nearest is one of them,
      // but we are at neither.
      final midLat = (_barakhamba.lat + _mandiHouse.lat) / 2;
      final midLon = (_barakhamba.lon + _mandiHouse.lon) / 2;
      final update = tracker.update(
        fix: RiderFix(
            lat: midLat, lon: midLon, accuracyMeters: 20, at: _now),
        now: _now,
      );

      expect(tracker.reachedIndex, -1,
          reason: 'nearest-station alone would wrongly mark one as reached');
      expect(update.nextStation?.name, 'Rajiv Chowk');
    });
  });

  group('the end of the line', () {
    test('the last station is announced as get-off, not next', () {
      final tracker = JourneyTracker(stations: _route);
      tracker.update(fix: _at(_mandiHouse), now: _now);
      final update = tracker.update(fix: _at(_mandiHouse), now: _now);

      expect(update.isFinalStation, isTrue);
      expect(update.headline, 'Get off at Supreme Court');
    });

    test('arriving ends the journey rather than pointing at nothing', () {
      final tracker = JourneyTracker(stations: _route);
      tracker.update(fix: _at(_supremeCourt), now: _now);
      final update = tracker.update(fix: _at(_supremeCourt), now: _now);

      expect(update.nextStation, isNull);
      expect(update.stationsRemaining, 0);
      expect(update.headline, 'Journey complete');
    });

    test('an empty route says nothing rather than crashing', () {
      final tracker = JourneyTracker(stations: const []);
      final update = tracker.update(fix: null, now: _now);
      expect(update.nextStation, isNull);
      expect(update.headline, 'Journey complete');
    });
  });
}

// The two sources that survive a tunnel.
void _undergroundSources() {
  group('a coarse wifi fix is used when it is still decisive', () {
    test('300 m accuracy resolves stations 1 km apart, and says it is rough',
        () {
      final tracker = JourneyTracker(stations: _route);
      // Barakhamba -> Mandi House is roughly 1 km, so half that spacing is a
      // ~500 m budget: a 300 m fix picks the right station beyond doubt.
      final update = tracker.update(
        fix: RiderFix(
            lat: _mandiHouse.lat,
            lon: _mandiHouse.lon,
            accuracyMeters: 300,
            at: _now),
        now: _now,
      );

      expect(update.source, TrackingSource.approximate);
      expect(update.sourceLabel, contains('wifi'));
      expect(update.sourceLabel, contains('approximate'),
          reason: 'a wifi fix must never read like a satellite one');
    });

    test('a fix too coarse for the local spacing is still refused', () {
      final tracker = JourneyTracker(stations: _route);
      final update = tracker.update(
        fix: RiderFix(
            lat: _mandiHouse.lat,
            lon: _mandiHouse.lon,
            accuracyMeters: 5000,
            at: _now),
        now: _now,
      );
      expect(update.source, isNot(TrackingSource.approximate));
      expect(update.source, TrackingSource.schedule);
    });

    test('a precise fix is still reported as gps, not downgraded', () {
      final tracker = JourneyTracker(stations: _route);
      final update = tracker.update(fix: _at(_mandiHouse), now: _now);
      expect(update.source, TrackingSource.gps);
    });
  });

  group('counted stops beat the timetable underground', () {
    test('stops counted from the accelerometer advance the journey', () {
      final tracker = JourneyTracker(stations: _route);
      final update = tracker.update(
        fix: null,
        now: _now,
        stopsCounted: 2,
        scheduleIndex: 0,
      );

      expect(update.source, TrackingSource.stopCount);
      expect(update.nextStation?.name, 'Supreme Court');
      expect(update.sourceLabel, contains('Counted from stops'));
    });

    test('counted stops outrank the schedule when they disagree', () {
      // The point of the feature: a held train keeps "advancing" on paper.
      // What the phone FELT is evidence; what the timetable assumed is not.
      final tracker = JourneyTracker(stations: _route);
      final update = tracker.update(
        fix: null, now: _now, stopsCounted: 1, scheduleIndex: 3,
      );
      expect(update.nextStation?.name, 'Mandi House',
          reason: 'the rider has felt one stop, not three');
    });

    test('counted stops still cannot rewind confirmed progress', () {
      final tracker = JourneyTracker(stations: _route);
      tracker.update(fix: _at(_mandiHouse), now: _now); // GPS-confirmed at #2

      final update = tracker.update(fix: null, now: _now, stopsCounted: 0);

      expect(tracker.reachedIndex, 2);
      expect(update.nextStation?.name, 'Supreme Court');
    });

    test('no motion signal at all falls back to the timetable, labelled', () {
      final tracker = JourneyTracker(stations: _route);
      final update = tracker.update(fix: null, now: _now, scheduleIndex: 1);
      expect(update.source, TrackingSource.schedule);
      expect(update.sourceLabel, contains('timetable'));
    });
  });
}
