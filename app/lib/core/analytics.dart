// Product analytics for the beta: what riders actually do, without learning
// where they go.
//
// The backend half of this has existed for a while (analytics_events, the
// batched /analytics/events endpoint, retention pruning). The client half did
// not, which is why four of the five beta metrics were unmeasurable: the app
// simply never emitted anything.
//
// Two rules shape everything below, and both are enforced structurally rather
// than by good intentions:
//
//   1. FAIL CLOSED. Nothing is buffered, let alone sent, unless consent is
//      explicitly true. Not "collect now, decide later" — an event that was
//      never recorded cannot leak. [AnalyticsService.record] is the only way
//      in and it checks first, so there is no path that skips the gate.
//
//   2. THE API CANNOT EXPRESS THE PRIVATE THING. The recording methods take
//      no free text and no identifiers. [recordSearch] accepts a query
//      *length*, not a query; [recordVoiceIntent] accepts an intent *name*,
//      not a transcript. A future caller cannot accidentally send a rider's
//      destination, because there is no parameter to put it in.
//
// The published privacy policy currently enumerates what MetroPulse collects
// and ends "That's the whole list" — and product analytics is not on it. So
// this stays off until that document is amended and the rider agrees. See
// docs/analytics_consent.md.

import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';

/// The event vocabulary, in one place so it can be audited at a glance.
///
/// Naming is `noun_verb` and deliberately coarse: these answer "is the beta
/// working?", not "what is this person doing?". Anything finer would be a
/// different product with a different privacy posture.
abstract final class AnalyticsEvents {
  /// App brought to the foreground. The basis for daily-usage counts.
  static const appOpened = 'app_opened';

  /// A journey was started from a plan.
  static const journeyStarted = 'journey_started';

  /// Journey Mode reached the destination and the rider confirmed arrival.
  static const journeyCompleted = 'journey_completed';

  /// Journey Mode was ended before arriving.
  static const journeyAbandoned = 'journey_abandoned';

  /// The voice assistant recognised an intent.
  static const voiceIntent = 'voice_intent';

  /// The voice assistant heard something it could not map to an intent.
  static const voiceIntentUnrecognised = 'voice_intent_unrecognised';

  /// A station search produced results and the rider picked one.
  static const searchSelected = 'search_selected';

  /// A station search produced nothing the rider wanted.
  static const searchAbandoned = 'search_abandoned';
}

/// One buffered event.
@immutable
class AnalyticsEvent {
  const AnalyticsEvent({
    required this.eventType,
    required this.occurredAt,
    this.payload,
  });

  final String eventType;
  final DateTime occurredAt;
  final Map<String, Object?>? payload;

  Map<String, Object?> toJson() => {
        'event_type': eventType,
        'occurred_at': occurredAt.toUtc().toIso8601String(),
        if (payload != null) 'payload': payload,
      };
}

/// Uploads a batch of events. Returns true when the batch was accepted, so
/// the service knows whether it may drop them.
typedef AnalyticsUploader = Future<bool> Function(
  List<AnalyticsEvent> batch,
  String sessionId,
);

/// Buffers events and uploads them in batches.
///
/// Deliberately in-memory only. Persisting a queue across launches would mean
/// events surviving a consent withdrawal, and a rider who turns this off is
/// entitled to expect that what they did yesterday is not still sitting on
/// disk waiting for a network. Losing a few events on a hard kill is the
/// cheaper mistake.
class AnalyticsService {
  AnalyticsService({
    required AnalyticsUploader uploader,
    required bool Function() consentGranted,
    int batchSize = 25,
    Duration flushInterval = const Duration(minutes: 2),
    int maxBuffered = 200,
    Random? random,
  })  : _uploader = uploader,
        _consentGranted = consentGranted,
        _batchSize = batchSize,
        _flushInterval = flushInterval,
        _maxBuffered = maxBuffered,
        // Per-run, not persisted: this groups one app session's events
        // together without becoming a stable identifier that outlives the
        // anonymous account id already disclosed in the privacy policy.
        _sessionId = _newSessionId(random ?? Random());

  final AnalyticsUploader _uploader;
  final bool Function() _consentGranted;
  final int _batchSize;
  final Duration _flushInterval;
  final int _maxBuffered;
  final String _sessionId;

  final List<AnalyticsEvent> _buffer = [];
  Timer? _timer;
  bool _sending = false;

  @visibleForTesting
  String get sessionId => _sessionId;

  @visibleForTesting
  int get bufferedCount => _buffer.length;

  static String _newSessionId(Random random) {
    const alphabet = 'abcdefghijklmnopqrstuvwxyz0123456789';
    return List.generate(16, (_) => alphabet[random.nextInt(alphabet.length)]).join();
  }

  /// The single entry point. Drops the event entirely when consent is absent.
  void record(String eventType, {Map<String, Object?>? payload, DateTime? at}) {
    if (!_consentGranted()) return;
    if (_buffer.length >= _maxBuffered) {
      // A long offline stretch must not grow without bound. Drop the OLDEST:
      // the newest events are the ones still worth having, and an unbounded
      // buffer on a phone is how an analytics client becomes the bug.
      _buffer.removeAt(0);
    }
    _buffer.add(AnalyticsEvent(
      eventType: eventType,
      occurredAt: at ?? DateTime.now(),
      payload: payload,
    ));
    if (_buffer.length >= _batchSize) {
      unawaited(flush());
    } else {
      _scheduleFlush();
    }
  }

  void _scheduleFlush() {
    _timer ??= Timer(_flushInterval, () {
      _timer = null;
      unawaited(flush());
    });
  }

  /// Uploads whatever is buffered. Safe to call at any time; never throws.
  Future<void> flush() async {
    _timer?.cancel();
    _timer = null;
    if (_sending || _buffer.isEmpty) return;
    if (!_consentGranted()) {
      // Consent was withdrawn while events sat in the buffer. They must not
      // be sent, and they must not be kept.
      _buffer.clear();
      return;
    }
    _sending = true;
    try {
      while (_buffer.isNotEmpty) {
        final batch = _buffer.take(_batchSize).toList(growable: false);
        final accepted = await _uploader(batch, _sessionId);
        if (!accepted) return; // offline or rejected: keep them for next time
        _buffer.removeRange(0, batch.length);
      }
    } finally {
      _sending = false;
    }
  }

  /// Discards everything buffered without sending it — call when the rider
  /// turns analytics off.
  void discard() {
    _timer?.cancel();
    _timer = null;
    _buffer.clear();
  }

  void dispose() {
    _timer?.cancel();
    _timer = null;
  }

  // -- typed recorders --------------------------------------------------------
  //
  // These exist so the private thing is unrepresentable, not merely
  // discouraged. Note what each one does NOT take.

  void recordAppOpened() => record(AnalyticsEvents.appOpened);

  void recordJourneyStarted({required int legCount, required bool stepFree}) =>
      record(AnalyticsEvents.journeyStarted, payload: {
        'leg_count': legCount,
        'step_free_preferred': stepFree,
      });

  /// Journey outcome. Takes a duration and whether the rider finished — never
  /// the origin or destination, which the journey record already holds
  /// server-side under the disclosed journey-history collection.
  void recordJourneyEnded({
    required bool completed,
    required Duration elapsed,
  }) =>
      record(
        completed
            ? AnalyticsEvents.journeyCompleted
            : AnalyticsEvents.journeyAbandoned,
        payload: {'elapsed_minutes': elapsed.inMinutes},
      );

  /// Voice usage. [intent] is an intent *name* from the local intent engine
  /// (e.g. "planJourney"), never the transcript and never what was searched
  /// for. Pass null when nothing was recognised.
  void recordVoiceIntent(String? intent) {
    if (intent == null) {
      record(AnalyticsEvents.voiceIntentUnrecognised);
      return;
    }
    record(AnalyticsEvents.voiceIntent, payload: {'intent': intent});
  }

  /// Search behaviour, as shape rather than content.
  ///
  /// There is no `query` parameter and there never should be: on a transit app
  /// the query IS the destination, and a destination is the most sensitive
  /// thing a rider hands us. What we can learn without it is the thing we
  /// actually wanted — whether search finds what people mean, and how much
  /// typing it costs them.
  void recordSearchSelected({
    required int queryLength,
    required int resultRank,
    required int resultCount,
  }) =>
      record(AnalyticsEvents.searchSelected, payload: {
        'query_length': queryLength,
        'result_rank': resultRank,
        'result_count': resultCount,
      });

  void recordSearchAbandoned({
    required int queryLength,
    required int resultCount,
  }) =>
      record(AnalyticsEvents.searchAbandoned, payload: {
        'query_length': queryLength,
        'result_count': resultCount,
      });
}
