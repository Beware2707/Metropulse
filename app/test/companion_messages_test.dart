import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/companion_messages.dart';

CompanionMessage? _build({
  bool arrived = false,
  bool arrivingSoon = false,
  String? exitName,
  bool approachingInterchange = false,
  String? interchangeStationName,
  bool justBoarded = false,
  int? recommendedCoach,
  String? platformHint,
  String? nextStationName,
}) {
  return buildCompanionMessage(
    arrived: arrived,
    arrivingSoon: arrivingSoon,
    exitName: exitName,
    approachingInterchange: approachingInterchange,
    interchangeStationName: interchangeStationName,
    justBoarded: justBoarded,
    recommendedCoach: recommendedCoach,
    platformHint: platformHint,
    nextStationName: nextStationName,
  );
}

void main() {
  test('arrived beats every other state', () {
    final message = _build(
      arrived: true,
      arrivingSoon: true,
      approachingInterchange: true,
      interchangeStationName: 'X',
      nextStationName: 'Y',
    );
    expect(message, const CompanionMessage(kind: CompanionMessageKind.arrived, text: 'You have arrived.'));
  });

  test('arriving soon mentions the exit when known', () {
    final withExit = _build(arrivingSoon: true, exitName: 'Gate 4');
    expect(withExit?.kind, CompanionMessageKind.arriving);
    expect(withExit?.text, contains('Gate 4'));

    final withoutExit = _build(arrivingSoon: true);
    expect(withoutExit?.text, isNot(contains('Gate')));
    expect(withoutExit?.text, contains('this is your stop'));
  });

  test('arriving soon beats an interchange flag (should never co-occur, but priority is defined)', () {
    final message = _build(
      arrivingSoon: true,
      approachingInterchange: true,
      interchangeStationName: 'Rajiv Chowk',
    );
    expect(message?.kind, CompanionMessageKind.arriving);
  });

  test('interchange message names the station', () {
    final message = _build(approachingInterchange: true, interchangeStationName: 'Rajiv Chowk');
    expect(message, const CompanionMessage(
      kind: CompanionMessageKind.interchange,
      text: 'Prepare to interchange at Rajiv Chowk.',
    ));
  });

  test('interchange flag without a station name falls through', () {
    final message = _build(approachingInterchange: true, nextStationName: 'Somewhere');
    expect(message?.kind, CompanionMessageKind.nextStation);
  });

  test('boarding message never invents a platform number', () {
    final withHint = _build(justBoarded: true, recommendedCoach: 4, platformHint: 'Towards Delta');
    expect(withHint?.text, 'Board Coach 5 — platform for Towards Delta.');
    expect(withHint?.text, isNot(contains('Platform 2')));

    final withoutHint = _build(justBoarded: true, recommendedCoach: 4);
    expect(withoutHint?.text, 'Board Coach 5.');
  });

  test('next station is the routine fallback', () {
    final message = _build(nextStationName: 'Hauz Khas');
    expect(message, const CompanionMessage(
      kind: CompanionMessageKind.nextStation,
      text: 'Next station is Hauz Khas.',
    ));
  });

  test('returns null when there is nothing to proactively say', () {
    expect(_build(), isNull);
  });
}
