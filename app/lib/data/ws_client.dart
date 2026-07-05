import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../domain/models/ws_message.dart';

enum WsStatus { connecting, live, reconnecting }

/// WebSocket client for `/ws/live`.
///
/// - subscribes with the last seen sequence so reconnects replay missed diffs
///   (the server sends a fresh snapshot when the gap is too old);
/// - watchdog: server heartbeats arrive every ~20 s, so a silent minute means
///   the connection is dead even if the socket looks open;
/// - exponential backoff reconnect. Never polls.
class LiveWsClient {
  LiveWsClient({required this.url});

  final String url;

  final _messages = StreamController<WsMessage>.broadcast();
  final _status = StreamController<WsStatus>.broadcast();

  Stream<WsMessage> get messages => _messages.stream;
  Stream<WsStatus> get status => _status.stream;

  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _watchdog;
  Timer? _reconnectTimer;
  int? _lastSeq;
  int _backoffSeconds = 1;
  bool _closed = false;

  bool _suspended = false;

  /// Battery saver: drop the socket while the app is backgrounded. The
  /// stored `last_seq` means resuming replays exactly what was missed.
  void suspend() {
    if (_suspended || _closed) return;
    _suspended = true;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _teardownSocket();
  }

  /// Reconnect after [suspend]; a no-op when already live.
  void resume() {
    if (!_suspended || _closed) return;
    _suspended = false;
    _backoffSeconds = 1;
    connect();
  }

  void connect() {
    if (_closed || _suspended) return;
    _status.add(WsStatus.connecting);
    try {
      final channel = WebSocketChannel.connect(Uri.parse(url));
      _channel = channel;
      channel.sink.add(jsonEncode({'type': 'subscribe', 'last_seq': _lastSeq}));
      _subscription = channel.stream.listen(
        _onFrame,
        onError: (Object _) => _scheduleReconnect(),
        onDone: _scheduleReconnect,
        cancelOnError: true,
      );
      _armWatchdog();
    } on Exception {
      _scheduleReconnect();
    }
  }

  void _onFrame(dynamic frame) {
    _armWatchdog();
    if (frame is! String) return;
    final Map<String, dynamic> json;
    try {
      json = jsonDecode(frame) as Map<String, dynamic>;
    } on FormatException {
      return;
    }
    final message = WsMessage.fromJson(json);
    if (message == null) return;
    _backoffSeconds = 1;
    _status.add(WsStatus.live);
    switch (message) {
      case WsSnapshot(:final seq):
        _lastSeq = seq;
      case WsUpdate(:final seq):
        _lastSeq = seq;
      case WsHeartbeat():
        _channel?.sink.add(jsonEncode({'type': 'pong'}));
      case WsAlert():
        break;
    }
    _messages.add(message);
  }

  void _armWatchdog() {
    _watchdog?.cancel();
    _watchdog = Timer(const Duration(seconds: 60), _scheduleReconnect);
  }

  void _scheduleReconnect() {
    if (_closed || _suspended || _reconnectTimer != null) return;
    _status.add(WsStatus.reconnecting);
    _teardownSocket();
    _reconnectTimer = Timer(Duration(seconds: _backoffSeconds), () {
      _reconnectTimer = null;
      _backoffSeconds = (_backoffSeconds * 2).clamp(1, 30);
      connect();
    });
  }

  void _teardownSocket() {
    _watchdog?.cancel();
    _subscription?.cancel();
    _subscription = null;
    _channel?.sink.close();
    _channel = null;
  }

  Future<void> dispose() async {
    _closed = true;
    _reconnectTimer?.cancel();
    _teardownSocket();
    await _messages.close();
    await _status.close();
  }
}
