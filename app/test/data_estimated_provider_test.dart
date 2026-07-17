// The empty-table trap.
//
// `Iterable.any` returns FALSE on an empty collection. Three separate screens
// independently computed provenance as `trains.any((t) => t.isEstimated)`, so
// an empty train table meant "not estimated" -- and the pill went green LIVE.
//
// That state is not a startup blip. `WsStatus.live` is not gated on train data
// (ws_client fires it on any frame, and heartbeats keep it alive), while the
// table is empty on first build and again whenever the feed drains it: after
// service hours, or at a quiet station with nothing inbound. So "socket up,
// table empty" is stable, and it rendered a confident pulsing green LIVE plus
// "Dots are trains, moving live" over a deployment that has no realtime feed
// at all -- with every honesty caveat suppressed by the same false value.
//
// The golden tests cannot catch this: they pass `dataEstimated` explicitly and
// so never exercise the expression that computes it. These tests do.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/models/train.dart';
import 'package:metropulse_app/providers/live_providers.dart';

Train _train(String id, {required bool estimated, String? nextStopId}) => Train(
      vehicle: Vehicle(
        vehicleId: id,
        latitude: 28.6,
        longitude: 77.2,
        timestamp: DateTime.utc(2026, 7, 17, 10),
        source: estimated ? 'schedule_estimate' : 'realtime_gps',
      ),
      resolved: true,
      isStale: false,
      nextStation: nextStopId == null
          ? null
          : StationRef(stopId: nextStopId, name: 'Bravo', sequence: 2),
    );

ProviderContainer _containerWith(Map<String, Train> trains) {
  final container = ProviderContainer(
    overrides: [liveTrainsProvider.overrideWith(() => _StubTrains(trains))],
  );
  addTearDown(container.dispose);
  return container;
}

class _StubTrains extends LiveTrainsNotifier {
  _StubTrains(this._initial);
  final Map<String, Train> _initial;
  @override
  Map<String, Train> build() => _initial;
}

void main() {
  group('dataEstimatedProvider fails closed', () {
    test('an EMPTY train table is estimated, not live', () {
      final c = _containerWith(const {});
      expect(
        c.read(dataEstimatedProvider),
        isTrue,
        reason: 'No trains is not evidence of real GPS. `.any` on an empty '
            'collection returns false, which is what lit up a green LIVE '
            'badge over an empty map.',
      );
    });

    test('a table of estimated trains is estimated', () {
      final c = _containerWith({'a': _train('a', estimated: true)});
      expect(c.read(dataEstimatedProvider), isTrue);
    });

    test('a single estimated train among real ones is enough to caveat', () {
      final c = _containerWith({
        'a': _train('a', estimated: false),
        'b': _train('b', estimated: true),
      });
      expect(c.read(dataEstimatedProvider), isTrue);
    });

    test('only an all-real-GPS, non-empty table may claim live', () {
      final c = _containerWith({'a': _train('a', estimated: false)});
      expect(c.read(dataEstimatedProvider), isFalse);
    });
  });

  group('arrivalsEstimatedProvider fails closed', () {
    test('a station with NO inbound trains is estimated, not live', () {
      // The common case: a quiet station, or any station after service hours.
      final c = _containerWith({'a': _train('a', estimated: false, nextStopId: 'S9')});
      expect(
        c.read(arrivalsEstimatedProvider('S1')),
        isTrue,
        reason: 'An empty arrivals board must not suppress the caveat.',
      );
    });

    test('a station whose arrivals are all real GPS may claim live', () {
      final c = _containerWith({'a': _train('a', estimated: false, nextStopId: 'S1')});
      expect(c.read(arrivalsEstimatedProvider('S1')), isFalse);
    });

    test('a station with an estimated arrival is estimated', () {
      final c = _containerWith({'a': _train('a', estimated: true, nextStopId: 'S1')});
      expect(c.read(arrivalsEstimatedProvider('S1')), isTrue);
    });
  });
}
