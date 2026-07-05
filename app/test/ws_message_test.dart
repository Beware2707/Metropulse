import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/models/ws_message.dart';

Map<String, dynamic> _train(String id, {double lon = 77.01}) => {
      'vehicle': {
        'vehicle_id': id,
        'latitude': 28.6,
        'longitude': lon,
        'timestamp': '2026-07-05T10:00:00+00:00',
        'trip_id': 'T1',
        'route_id': 'R1',
      },
      'resolved': true,
      'is_stale': false,
      'route_long_name': 'Red Line',
      'route_color': 'EE1C25',
      'at_station': false,
      'next_station': {'stop_id': 'S3', 'name': 'Charlie', 'sequence': 3},
      'remaining_stations': [
        {'stop_id': 'S3', 'name': 'Charlie', 'sequence': 3},
        {'stop_id': 'S4', 'name': 'Delta', 'sequence': 4},
      ],
    };

void main() {
  test('parses snapshot frames', () {
    final message = WsMessage.fromJson({
      'type': 'snapshot',
      'seq': 12,
      'trains': [_train('v1')],
    });
    expect(message, isA<WsSnapshot>());
    final snapshot = message as WsSnapshot;
    expect(snapshot.seq, 12);
    expect(snapshot.trains.single.id, 'v1');
    expect(snapshot.trains.single.lineLabel, 'Red Line');
    expect(snapshot.trains.single.remainingStations, hasLength(2));
  });

  test('parses update frames with added/moved/removed/stale', () {
    final message = WsMessage.fromJson({
      'type': 'update',
      'seq': 13,
      'added': [_train('v2')],
      'moved': [_train('v1', lon: 77.02)],
      'removed': ['v0'],
      'stale': ['v3'],
    });
    expect(message, isA<WsUpdate>());
    final update = message as WsUpdate;
    expect(update.added.single.id, 'v2');
    expect(update.moved.single.vehicle.longitude, 77.02);
    expect(update.removed, ['v0']);
    expect(update.stale, ['v3']);
  });

  test('parses heartbeat and alert frames', () {
    expect(WsMessage.fromJson({'type': 'heartbeat'}), isA<WsHeartbeat>());
    final alert = WsMessage.fromJson({
      'type': 'alert',
      'alert': {'title': 'Delay', 'description': 'x', 'severity': 'warning'},
    });
    expect(alert, isA<WsAlert>());
    expect((alert as WsAlert).severity, 'warning');
  });

  test('unknown frame types are ignored, not fatal', () {
    expect(WsMessage.fromJson({'type': 'brand-new-thing'}), isNull);
    expect(WsMessage.fromJson({'no_type': true}), isNull);
  });
}
