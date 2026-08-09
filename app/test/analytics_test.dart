// The analytics client, tested for the things that would actually hurt a
// rider if they were wrong.
//
// This is collection code in a transit app: the failure mode isn't a wrong
// pixel, it's recording where somebody goes. So the tests here are mostly
// about what must NOT happen — no consent, no events; consent withdrawn,
// buffer destroyed; and no API surface capable of carrying a search query or
// a transcript in the first place.
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/core/analytics.dart';

/// Captures uploads instead of performing them.
class _FakeUploader {
  final List<List<AnalyticsEvent>> batches = [];
  final List<String> sessionIds = [];
  bool accept = true;

  Future<bool> call(List<AnalyticsEvent> batch, String sessionId) async {
    if (!accept) return false;
    batches.add(List.of(batch));
    sessionIds.add(sessionId);
    return true;
  }

  List<AnalyticsEvent> get allEvents => [for (final b in batches) ...b];
}

AnalyticsService _service(
  _FakeUploader uploader, {
  required bool Function() consent,
  int batchSize = 25,
  int maxBuffered = 200,
}) =>
    AnalyticsService(
      uploader: uploader.call,
      consentGranted: consent,
      batchSize: batchSize,
      maxBuffered: maxBuffered,
      flushInterval: const Duration(hours: 1), // never fires during a test
      random: Random(7),
    );

void main() {
  group('consent is a gate, not a preference', () {
    test('without consent nothing is even buffered', () async {
      final uploader = _FakeUploader();
      final service = _service(uploader, consent: () => false);

      service.recordAppOpened();
      service.recordVoiceIntent('planJourney');
      service.recordSearchSelected(queryLength: 4, resultRank: 0, resultCount: 9);
      await service.flush();

      expect(service.bufferedCount, 0,
          reason: 'an event never recorded cannot leak');
      expect(uploader.batches, isEmpty);
    });

    test('consent withdrawn mid-session destroys the buffer unsent', () async {
      final uploader = _FakeUploader();
      var granted = true;
      final service = _service(uploader, consent: () => granted);

      service.recordAppOpened();
      service.recordAppOpened();
      expect(service.bufferedCount, 2);

      granted = false;
      await service.flush();

      expect(uploader.batches, isEmpty, reason: 'must not send what was revoked');
      expect(service.bufferedCount, 0, reason: 'must not keep it either');
    });

    test('discard drops everything without sending', () async {
      final uploader = _FakeUploader();
      final service = _service(uploader, consent: () => true);
      service.recordAppOpened();
      service.discard();
      await service.flush();
      expect(uploader.batches, isEmpty);
      expect(service.bufferedCount, 0);
    });
  });

  group('what leaves the device', () {
    test('a search records shape, never the query', () async {
      final uploader = _FakeUploader();
      final service = _service(uploader, consent: () => true);

      service.recordSearchSelected(queryLength: 6, resultRank: 2, resultCount: 11);
      await service.flush();

      final payload = uploader.allEvents.single.payload!;
      expect(payload['query_length'], 6);
      expect(payload['result_rank'], 2);
      expect(payload['result_count'], 11);
      // On a transit app the query IS the destination.
      expect(payload.keys, isNot(contains('query')));
      expect(payload.values.whereType<String>(), isEmpty,
          reason: 'no free text may ride along in a search event');
    });

    test('voice records the intent name, never a transcript', () async {
      final uploader = _FakeUploader();
      final service = _service(uploader, consent: () => true);

      service.recordVoiceIntent('planJourney');
      service.recordVoiceIntent(null);
      await service.flush();

      final events = uploader.allEvents;
      expect(events[0].eventType, AnalyticsEvents.voiceIntent);
      expect(events[0].payload, {'intent': 'planJourney'});
      expect(events[1].eventType, AnalyticsEvents.voiceIntentUnrecognised);
      expect(events[1].payload, isNull,
          reason: 'nothing recognised means nothing to say about it');
    });

    test('a journey outcome carries duration, not origin or destination',
        () async {
      final uploader = _FakeUploader();
      final service = _service(uploader, consent: () => true);

      service.recordJourneyEnded(
          completed: true, elapsed: const Duration(minutes: 27));
      await service.flush();

      final event = uploader.allEvents.single;
      expect(event.eventType, AnalyticsEvents.journeyCompleted);
      expect(event.payload, {'elapsed_minutes': 27});
    });

    test('an abandoned journey is a distinct event, not a missing one', () async {
      final uploader = _FakeUploader();
      final service = _service(uploader, consent: () => true);
      service.recordJourneyEnded(
          completed: false, elapsed: const Duration(minutes: 4));
      await service.flush();
      expect(uploader.allEvents.single.eventType,
          AnalyticsEvents.journeyAbandoned);
    });
  });

  group('the buffer behaves on a bad network', () {
    test('a rejected upload keeps the batch for next time', () async {
      final uploader = _FakeUploader()..accept = false;
      final service = _service(uploader, consent: () => true);

      service.recordAppOpened();
      await service.flush();
      expect(service.bufferedCount, 1, reason: 'offline must not lose events');

      uploader.accept = true;
      await service.flush();
      expect(uploader.allEvents.length, 1);
      expect(service.bufferedCount, 0);
    });

    test('a long offline stretch drops the oldest, not the newest', () async {
      final uploader = _FakeUploader()..accept = false;
      final service = _service(uploader,
          consent: () => true, batchSize: 1000, maxBuffered: 3);

      for (var i = 0; i < 5; i++) {
        service.record('e$i');
      }
      expect(service.bufferedCount, 3);

      uploader.accept = true;
      await service.flush();
      expect([for (final e in uploader.allEvents) e.eventType], ['e2', 'e3', 'e4']);
    });

    test('reaching the batch size flushes without waiting for the timer',
        () async {
      final uploader = _FakeUploader();
      final service = _service(uploader, consent: () => true, batchSize: 3);

      service.record('a');
      service.record('b');
      expect(uploader.batches, isEmpty);
      service.record('c');
      await Future<void>.delayed(Duration.zero);

      expect(uploader.allEvents.length, 3);
    });
  });

  group('the session id', () {
    test('groups one run without persisting across runs', () async {
      final uploader = _FakeUploader();
      final a = _service(uploader, consent: () => true);
      a.recordAppOpened();
      await a.flush();

      final b = AnalyticsService(
        uploader: uploader.call,
        consentGranted: () => true,
        flushInterval: const Duration(hours: 1),
        random: Random(99),
      );
      b.recordAppOpened();
      await b.flush();

      expect(uploader.sessionIds[0], isNotEmpty);
      expect(uploader.sessionIds[0], isNot(uploader.sessionIds[1]),
          reason: 'a stable id across runs would be a tracker the privacy '
              'policy never disclosed');
    });
  });

  group('serialisation', () {
    test('timestamps are UTC ISO-8601 so the server can trust them', () {
      final event = AnalyticsEvent(
        eventType: AnalyticsEvents.appOpened,
        occurredAt: DateTime.utc(2026, 8, 4, 9, 30),
      );
      final json = event.toJson();
      expect(json['event_type'], 'app_opened');
      expect(json['occurred_at'], '2026-08-04T09:30:00.000Z');
      expect(json.containsKey('payload'), isFalse,
          reason: 'an absent payload is omitted, not sent as null');
    });
  });
}
