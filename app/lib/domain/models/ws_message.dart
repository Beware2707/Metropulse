import 'train.dart';

/// The `/ws/live` protocol, parsed into typed frames.
///
/// Hand-rolled (no codegen) because it is a sealed union over a tiny,
/// stable wire format — and it must never throw on unknown frame types.
sealed class WsMessage {
  const WsMessage();

  static WsMessage? fromJson(Map<String, dynamic> json) {
    switch (json['type']) {
      case 'snapshot':
        return WsSnapshot(
          seq: (json['seq'] as num?)?.toInt() ?? 0,
          trains: _trains(json['trains']),
        );
      case 'update':
        return WsUpdate(
          seq: (json['seq'] as num?)?.toInt() ?? 0,
          added: _trains(json['added']),
          moved: _trains(json['moved']),
          removed: _strings(json['removed']),
          stale: _strings(json['stale']),
        );
      case 'alert':
        final alert = json['alert'];
        if (alert is Map<String, dynamic>) {
          return WsAlert(
            title: alert['title'] as String? ?? 'Service alert',
            description: alert['description'] as String? ?? '',
            severity: alert['severity'] as String? ?? 'info',
            routeId: alert['route_id'] as String?,
          );
        }
        return null;
      case 'heartbeat':
        return const WsHeartbeat();
      default:
        return null; // forward-compatible: ignore unknown frames
    }
  }

  static List<Train> _trains(Object? value) {
    if (value is! List) return const [];
    return value
        .whereType<Map<String, dynamic>>()
        .map(Train.fromJson)
        .toList(growable: false);
  }

  static List<String> _strings(Object? value) {
    if (value is! List) return const [];
    return value.whereType<String>().toList(growable: false);
  }
}

class WsSnapshot extends WsMessage {
  const WsSnapshot({required this.seq, required this.trains});
  final int seq;
  final List<Train> trains;
}

class WsUpdate extends WsMessage {
  const WsUpdate({
    required this.seq,
    required this.added,
    required this.moved,
    required this.removed,
    required this.stale,
  });
  final int seq;
  final List<Train> added;
  final List<Train> moved;
  final List<String> removed;
  final List<String> stale;
}

class WsAlert extends WsMessage {
  const WsAlert({
    required this.title,
    required this.description,
    required this.severity,
    this.routeId,
  });
  final String title;
  final String description;
  final String severity;
  final String? routeId;
}

class WsHeartbeat extends WsMessage {
  const WsHeartbeat();
}
