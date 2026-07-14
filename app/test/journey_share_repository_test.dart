// Repository-contract test for the share + rider-report methods: exercises
// the real JourneyRepository / AlertsRepository against a stubbed Dio adapter
// (no live backend), asserting shareJourney parses the {token, share_url,
// expires_at} contract, riderReports flattens the {reports: [...]} envelope,
// and postRiderReport reports acceptance honestly.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:metropulse_app/data/api_client.dart';
import 'package:metropulse_app/data/local_store.dart';
import 'package:metropulse_app/data/repositories.dart';

/// Routes each request to a canned JSON response keyed by path fragment.
class _StubAdapter implements HttpClientAdapter {
  _StubAdapter(this.responder);

  final ResponseBody Function(RequestOptions options) responder;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async =>
      responder(options);

  @override
  void close({bool force = false}) {}
}

ResponseBody _json(Object body, int status) => ResponseBody.fromString(
      jsonEncode(body),
      status,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );

void main() {
  late Directory tempDir;
  late LocalStore store;

  setUpAll(() async {
    tempDir = Directory.systemTemp.createTempSync('mp_repo_test');
    Hive.init(tempDir.path);
    store = await LocalStore.open();
  });

  tearDownAll(() async {
    await Hive.close();
    tempDir.deleteSync(recursive: true);
  });

  ApiClient stubbedApi(ResponseBody Function(RequestOptions) responder) {
    final api = ApiClient(store);
    api.dio.httpClientAdapter = _StubAdapter(responder);
    return api;
  }

  test('shareJourney parses the token / share_url / expires_at contract', () async {
    final api = stubbedApi((options) {
      expect(options.method, 'POST');
      expect(options.path, '/api/v1/me/journeys/7/share');
      return _json({
        'token': 'tok_abc',
        'share_url': 'https://metropulse.app/s/tok_abc',
        'expires_at': '2026-07-14T18:30:00Z',
      }, 201);
    });
    final repo = JourneyRepository(api, store);

    final share = await repo.shareJourney(7);

    expect(share, isNotNull);
    expect(share!['token'], 'tok_abc');
    expect(share['share_url'], 'https://metropulse.app/s/tok_abc');
    expect(share['expires_at'], '2026-07-14T18:30:00Z');
  });

  test('shareJourney returns null on a 404 (not the caller\'s active journey)', () async {
    final api = stubbedApi((_) => _json({'detail': 'not found'}, 404));
    final repo = JourneyRepository(api, store);

    expect(await repo.shareJourney(9), isNull);
  });

  test('riderReports flattens the reports envelope newest-first as given', () async {
    final api = stubbedApi((options) {
      expect(options.path, '/api/v1/alerts/reports');
      expect(options.queryParameters['since_minutes'], 120);
      return _json({
        'reports': [
          {
            'id': 2,
            'stop_id': 'STN9',
            'route_id': null,
            'message': 'Doors stuck',
            'category': 'other',
            'reported_at': '2026-07-14T17:00:00Z',
            'count': 1,
          },
          {
            'id': 1,
            'stop_id': 'STN9',
            'route_id': null,
            'message': 'Long delay',
            'category': 'delay',
            'reported_at': '2026-07-14T16:55:00Z',
            'count': 4,
          },
        ],
      }, 200);
    });
    final repo = AlertsRepository(api);

    final reports = await repo.riderReports();

    expect(reports, hasLength(2));
    expect(reports.first['message'], 'Doors stuck');
    expect(reports.last['count'], 4);
  });

  test('postRiderReport sends the body and reports acceptance', () async {
    Map<String, dynamic>? sentBody;
    final api = stubbedApi((options) {
      expect(options.method, 'POST');
      expect(options.path, '/api/v1/alerts/reports');
      sentBody = options.data as Map<String, dynamic>;
      return _json({'report_id': 55}, 202);
    });
    final repo = AlertsRepository(api);

    final ok = await repo.postRiderReport(
      stopId: 'STN9',
      message: 'Held at platform',
      category: 'delay',
    );

    expect(ok, isTrue);
    expect(sentBody!['stop_id'], 'STN9');
    expect(sentBody!['message'], 'Held at platform');
    expect(sentBody!['category'], 'delay');
    // Optional fields absent when not supplied.
    expect(sentBody!.containsKey('route_id'), isFalse);
  });
}
