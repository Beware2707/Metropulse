// The empty arrivals board must not blame the metro for our missing data.
//
// DMRC's GTFS schedules 0 trips on Sundays (5,379 weekday, 59 Saturday). So
// every Sunday the board is empty, and it used to say "No trains headed this
// way right now" — which reads as *the service has stopped*. It hasn't. This
// pins the distinction, and the fallback direction: when we don't KNOW whether
// today is covered, we must not invent a reason.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/core/widgets/empty_state.dart';
import 'package:metropulse_app/data/ws_client.dart';
import 'package:metropulse_app/features/station/station_detail_screen.dart';
import 'package:metropulse_app/providers/core_providers.dart';
import 'package:metropulse_app/providers/live_providers.dart';

Future<String> _messageFor(
  WidgetTester tester, {
  required bool? hasTimetable,
  WsStatus status = WsStatus.live,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        wsStatusProvider.overrideWith((ref) => Stream.value(status)),
        hasTimetableTodayProvider.overrideWith((ref) async => hasTimetable),
      ],
      child: const MaterialApp(home: Scaffold(body: EmptyArrivalsForTest())),
    ),
  );
  await tester.pump();
  await tester.pump();
  return tester.widget<EmptyState>(find.byType(EmptyState)).message;
}

void main() {
  testWidgets('a day the timetable omits says so, and does not blame the metro',
      (tester) async {
    final message = await _messageFor(tester, hasTimetable: false);

    expect(message, contains('no service data for today'));
    expect(message, contains('may still be running'),
        reason: 'a rider must not conclude the metro has stopped');
    expect(message, isNot(contains('No trains headed this way')));
  });

  testWidgets('a covered day with nothing approaching keeps the plain wording',
      (tester) async {
    final message = await _messageFor(tester, hasTimetable: true);
    expect(message, 'No trains headed this way right now.');
  });

  testWidgets('not knowing is not a licence to guess a reason', (tester) async {
    // Offline or still loading: null. Claiming "no data for today" here would
    // be inventing a cause, which is the same failure in the other direction.
    final message = await _messageFor(tester, hasTimetable: null);
    expect(message, 'No trains headed this way right now.');
  });

  testWidgets('a connection still being established outranks everything',
      (tester) async {
    final message = await _messageFor(
      tester,
      hasTimetable: false,
      status: WsStatus.connecting,
    );
    expect(message, 'Connecting to live arrivals…',
        reason: 'we cannot know what today holds before we have connected');
  });
}
