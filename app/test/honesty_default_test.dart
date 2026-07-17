// The honesty contract, at the one place it can silently break.
//
// MetroPulse has no DMRC realtime feed: every position is interpolated from
// the timetable and tagged source="schedule_estimate". `Vehicle.isEstimated`
// is what drives the LiveIndicator's amber SCHEDULE pill instead of a green
// LIVE one, so if `source` ever resolves wrongly, the app tells its one
// forbidden lie.
//
// `source` used to default to 'realtime_gps'. That default failed OPEN: any
// payload without the field — an old cache, schema drift, an explicit null —
// deserialized to "this is real GPS" and lit up LIVE. Nothing caught it,
// because every fixture in the suite omitted `source` and therefore tested a
// train state that cannot exist in production.
//
// These tests pin the safe direction: absent/unknown/null => estimated.
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/models/train.dart';

Map<String, dynamic> _vehicleJson({Object? source = _absent}) => {
      'vehicle_id': 'V1',
      'latitude': 28.6,
      'longitude': 77.2,
      'timestamp': '2026-07-17T10:00:00+00:00',
      if (!identical(source, _absent)) 'source': source,
    };

const _absent = Object();

void main() {
  group('Vehicle.isEstimated fails closed', () {
    test('a payload with NO source field is treated as estimated, not live', () {
      final v = Vehicle.fromJson(_vehicleJson());
      expect(
        v.source,
        'schedule_estimate',
        reason: 'A missing source must never be assumed to be real GPS.',
      );
      expect(v.isEstimated, isTrue);
    });

    test('an explicit null source is treated as estimated', () {
      final v = Vehicle.fromJson(_vehicleJson(source: null));
      expect(v.isEstimated, isTrue);
    });

    test('an unknown source value is treated as estimated', () {
      final v = Vehicle.fromJson(_vehicleJson(source: 'something_new'));
      expect(
        v.isEstimated,
        isTrue,
        reason: 'Only an explicit realtime_gps may claim to be live.',
      );
    });

    test('schedule_estimate is estimated', () {
      expect(Vehicle.fromJson(_vehicleJson(source: 'schedule_estimate')).isEstimated, isTrue);
    });

    test('realtime_gps is the ONLY value that claims live', () {
      final v = Vehicle.fromJson(_vehicleJson(source: 'realtime_gps'));
      expect(v.isEstimated, isFalse);
    });
  });
}
