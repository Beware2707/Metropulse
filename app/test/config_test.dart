// The shipped API base must be reachable from a real phone.
//
// This exists because it wasn't. `defaultApiBase` was `http://10.0.2.2:8000`
// — the Android emulator's alias for the host machine's localhost. It works
// beautifully on an emulator and is unroutable from every real device, so
// release APKs shipped pointed at a developer's laptop: WebSocket refused on
// a loop, badge stuck on CONNECTING then RECONNECTING, empty home screen. The
// Settings override that could have rescued it is gated behind kDebugMode, so
// the user had no way out.
//
// Nothing failed when that regressed. Every unit and widget test injects its
// own base URL, and the emulator this was checked on could reach 10.0.2.2 —
// so the one environment where the bug is invisible was the environment it
// was verified in. Hence a test that asserts the constant itself.
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/core/config.dart';

void main() {
  group('the default API base is reachable from a real device', () {
    test('is not the emulator host alias', () {
      expect(AppConfig.defaultApiBase, isNot(contains('10.0.2.2')),
          reason: '10.0.2.2 is the emulator alias for the host machine and '
              'resolves to nothing on a real phone');
    });

    test('is not loopback', () {
      final base = AppConfig.defaultApiBase.toLowerCase();
      for (final loopback in ['localhost', '127.0.0.1', '0.0.0.0', '::1']) {
        expect(base, isNot(contains(loopback)),
            reason: '$loopback points a phone at itself');
      }
    });

    test('is not a private LAN address', () {
      // 192.168.x, 10.x and 172.16-31.x are someone's home network: fine for
      // development, silently broken for anyone else.
      final host = Uri.parse(AppConfig.defaultApiBase).host;
      expect(RegExp(r'^192\.168\.').hasMatch(host), isFalse, reason: host);
      expect(RegExp(r'^10\.').hasMatch(host), isFalse, reason: host);
      expect(RegExp(r'^172\.(1[6-9]|2\d|3[01])\.').hasMatch(host), isFalse,
          reason: host);
    });

    test('is an absolute http(s) URL with a host and no trailing slash', () {
      final uri = Uri.parse(AppConfig.defaultApiBase);
      expect(uri.hasScheme, isTrue);
      expect(uri.scheme, anyOf('http', 'https'));
      expect(uri.host, isNotEmpty);
      expect(AppConfig.defaultApiBase, isNot(endsWith('/')),
          reason: 'paths are joined onto this, so a trailing slash doubles up');
    });
  });

  group('the websocket URL is derived from the API base', () {
    test('http becomes ws and https becomes wss', () {
      expect(AppConfig.wsUrlFor('http://example.test:8000'), startsWith('ws://'));
      expect(AppConfig.wsUrlFor('https://example.test'), startsWith('wss://'));
    });

    test('a plaintext scheme never survives into a secure page', () {
      // If the base is ever moved to https, the socket must move with it —
      // a wss page opening a ws socket is blocked by the platform.
      expect(AppConfig.wsUrlFor('https://example.test'), isNot(contains('ws://')));
    });

    test('the real default produces a usable socket URL', () {
      final ws = AppConfig.wsUrlFor(AppConfig.defaultApiBase);
      expect(ws, anyOf(startsWith('ws://'), startsWith('wss://')));
      expect(ws, isNot(contains('10.0.2.2')));
    });
  });
}
