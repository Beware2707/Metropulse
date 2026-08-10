import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/voice_intent.dart';

void main() {
  _fieldReportedPhrasings();

  test('recognises "how do I reach" as a routeTo query with the place extracted', () {
    final intent = parseVoiceIntent('How do I reach AIIMS?');
    expect(intent.kind, VoiceIntentKind.routeTo);
    expect(intent.stationQuery, 'aiims');
  });

  test('recognises "take me to" as routeTo', () {
    final intent = parseVoiceIntent('take me to Rajiv Chowk');
    expect(intent.kind, VoiceIntentKind.routeTo);
    expect(intent.stationQuery, 'rajiv chowk');
  });

  test('recognises "when should I leave"', () {
    expect(parseVoiceIntent('When should I leave?').kind, VoiceIntentKind.whenToLeave);
    expect(parseVoiceIntent('what time should I leave for work').kind, VoiceIntentKind.whenToLeave);
  });

  test('recognises "I\'m running late" as a distinct intent from "when should I leave"', () {
    expect(parseVoiceIntent("I'm running late").kind, VoiceIntentKind.runningLate);
    expect(parseVoiceIntent('running late for my train').kind, VoiceIntentKind.runningLate);
    expect(parseVoiceIntent('I am behind schedule').kind, VoiceIntentKind.runningLate);
    expect(parseVoiceIntent('When should I leave?').kind, VoiceIntentKind.whenToLeave);
  });

  test('recognises coach questions', () {
    expect(parseVoiceIntent('Which coach should I board?').kind, VoiceIntentKind.whichCoach);
    expect(parseVoiceIntent('what is the best coach').kind, VoiceIntentKind.whichCoach);
  });

  test('recognises next-station questions', () {
    expect(parseVoiceIntent('What is my next station?').kind, VoiceIntentKind.nextStation);
    expect(parseVoiceIntent("what's the next stop").kind, VoiceIntentKind.nextStation);
  });

  test('recognises fare questions', () {
    expect(parseVoiceIntent('How much fare?').kind, VoiceIntentKind.fareQuery);
    expect(parseVoiceIntent('how much will it cost').kind, VoiceIntentKind.fareQuery);
  });

  test('recognises "am I going the right way" as an on-track check', () {
    expect(parseVoiceIntent('Am I going the right way?').kind, VoiceIntentKind.onTrack);
    expect(parseVoiceIntent('is this the right train').kind, VoiceIntentKind.onTrack);
  });

  test('a routeTo trigger with no named place falls through to unknown', () {
    expect(parseVoiceIntent('how do I reach').kind, VoiceIntentKind.unknown);
  });

  test('off-topic questions are unknown, never guessed at', () {
    expect(parseVoiceIntent("What's the weather today?").kind, VoiceIntentKind.unknown);
    expect(parseVoiceIntent('Tell me a joke').kind, VoiceIntentKind.unknown);
    expect(parseVoiceIntent('').kind, VoiceIntentKind.unknown);
  });

  test('onTrack is checked before routeTo so "right way" never gets misread', () {
    final intent = parseVoiceIntent('am I going the right way to reach home');
    expect(intent.kind, VoiceIntentKind.onTrack);
  });
}

// Phrasings real riders used that the classifier silently dropped.
//
// Every one of these came back `unknown` in the field — the assistant said
// "I can only help with your Delhi Metro journey" to a plain request for a
// Delhi Metro journey. The route trigger was the literal string "route to",
// so "best route FROM x TO y" — the most natural way to ask — was the one
// phrasing guaranteed to fail.
void _fieldReportedPhrasings() {
  group('phrasings that used to fall through to unknown', () {
    for (final phrase in [
      'give me the best route from rajiv chowk to saket',
      "what's the best route from dwarka sector 10 to saket",
      'fastest route from mayur vihar 1 to hauz khas',
      'route from saket to rajiv chowk',
      'directions from saket to rajiv chowk',
    ]) {
      test('"$phrase" resolves both ends', () {
        final intent = parseVoiceIntent(phrase);
        expect(intent.kind, VoiceIntentKind.routeTo, reason: phrase);
        expect(intent.originQuery, isNotNull, reason: 'origin must be captured');
        expect(intent.stationQuery, isNotNull);
        // The destination must not swallow the origin, and vice versa.
        expect(intent.originQuery, isNot(contains(' to ')));
        expect(intent.stationQuery, isNot(startsWith('from')));
      });
    }

    test('origin and destination land the right way round', () {
      final intent = parseVoiceIntent('best route from rajiv chowk to saket');
      expect(intent.originQuery, 'rajiv chowk');
      expect(intent.stationQuery, 'saket');
    });

    test('a multi-word origin is not truncated at its first space', () {
      final intent = parseVoiceIntent('route from dwarka sector 10 to saket');
      expect(intent.originQuery, 'dwarka sector 10');
      expect(intent.stationQuery, 'saket');
    });
  });

  group('starting a new journey', () {
    for (final phrase in [
      'set up a new journey',
      'setup a new journey',
      'start a new journey',
      'plan a journey',
      'plan a trip',
      'create a new trip',
      'new journey',
    ]) {
      test('"$phrase" opens the planner', () {
        expect(parseVoiceIntent(phrase).kind, VoiceIntentKind.planJourney,
            reason: phrase);
      });
    }

    test('naming a destination still routes, rather than opening a blank form',
        () {
      final intent = parseVoiceIntent('plan a trip to saket');
      expect(intent.kind, VoiceIntentKind.routeTo);
      expect(intent.stationQuery, 'saket');
    });
  });

  group('destination-only requests still work', () {
    test('"take me to saket" needs no origin', () {
      final intent = parseVoiceIntent('take me to saket');
      expect(intent.kind, VoiceIntentKind.routeTo);
      expect(intent.stationQuery, 'saket');
      expect(intent.originQuery, isNull, reason: 'falls back to Home');
    });

    test('off-topic is still declined', () {
      expect(parseVoiceIntent('what is the weather').kind,
          VoiceIntentKind.unknown);
    });
  });
}
