// The ongoing notification's wording — the one surface where a wrong claim
// has a physical cost, because a rider stands up because of it.
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/journey_tracking.dart';
import 'package:metropulse_app/domain/tracking_notification.dart';

const _saket = TrackedStation(
    stopId: '9', name: 'Saket', lat: 28.5203, lon: 77.2190, underground: true);

TrackingUpdate _update({
  required TrackingSource source,
  bool approaching = false,
  bool finalStation = false,
  int remaining = 3,
  double? metres,
}) =>
    TrackingUpdate(
      nextStation: _saket,
      stationsRemaining: remaining,
      source: source,
      isApproaching: approaching,
      isFinalStation: finalStation,
      metresToNext: metres,
    );

void main() {
  test('every notification states where its knowledge came from', () {
    for (final source in TrackingSource.values) {
      final note = buildTrackingNotification(_update(source: source));
      expect(note.body, isNotEmpty, reason: '$source');
      // The provenance line is not decoration — it must survive into the body.
      expect(note.body, contains('·'), reason: '$source');
    }
  });

  test('a GPS-tracked approach earns the urgent title', () {
    final note = buildTrackingNotification(_update(
      source: TrackingSource.gps,
      approaching: true,
      finalStation: true,
      remaining: 1,
      metres: 400,
    ));
    expect(note.title, 'Get off next — Saket');
    expect(note.body, contains('From your location'));
  });

  test('the timetable never earns it', () {
    // Same journey position, no fix. "Get off next" from a schedule is an
    // instruction backed by a guess, and this is the moment it would hurt.
    final note = buildTrackingNotification(_update(
      source: TrackingSource.schedule,
      approaching: false,
      finalStation: true,
      remaining: 1,
    ));
    expect(note.title, isNot(contains('Get off next')));
    expect(note.title, 'Get off at Saket');
    expect(note.body, contains('no GPS signal'));
  });

  test('counted stops are named as such, not passed off as a fix', () {
    final note = buildTrackingNotification(
        _update(source: TrackingSource.stopCount, remaining: 2));
    expect(note.body, contains('Counted from stops'));
    expect(note.body, isNot(contains('From your location')));
  });

  test('a wifi fix is labelled approximate', () {
    final note = buildTrackingNotification(
        _update(source: TrackingSource.approximate, remaining: 2));
    expect(note.body, contains('approximate'));
  });

  test('one stop reads as singular', () {
    final note = buildTrackingNotification(
        _update(source: TrackingSource.gps, remaining: 1, metres: 900));
    expect(note.body, startsWith('1 stop away'));
  });

  test('arrival stops instructing and offers the exit', () {
    const done = TrackingUpdate(
      nextStation: null,
      stationsRemaining: 0,
      source: TrackingSource.gps,
      isApproaching: false,
      isFinalStation: false,
    );
    final note = buildTrackingNotification(done);
    expect(note.title, 'Journey complete');
  });
}
