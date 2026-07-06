import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/voice_intent.dart';

void main() {
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
