// The Namo Bharat connection card.
//
// NCRTC's feed is a community reconstruction with a synthesised timetable, so
// the card must (a) label its times indicative and credit the producer,
// (b) never call a long walk an "interchange", and (c) state plainly that
// this is a different operator with a different ticket.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/core/theme.dart';
import 'package:metropulse_app/features/station/station_detail_screen.dart';

Future<void> _pump(WidgetTester tester, Map<String, dynamic> c) async {
  await tester.pumpWidget(MaterialApp(
    theme: buildLightTheme(),
    home: Scaffold(body: regionalRailDetailForTest(c)),
  ));
  await tester.pump();
}

Map<String, dynamic> _conn({int distance = 338}) => <String, dynamic>{
      'operator': 'NCRTC',
      'service_name': 'Namo Bharat',
      'rail_station_name': 'Ghaziabad',
      'distance_m': distance,
      'headway_minutes': 15,
      'first_departure': '06:04:29',
      'last_departure': '22:25:08',
      'source': 'OpenStreetMap contributors',
      'times_indicative': true,
    };

void main() {
  testWidgets('a short walk is an interchange, with indicative times',
      (tester) async {
    await _pump(tester, _conn());
    expect(find.textContaining('Interchange · 338m walk'), findsOneWidget);
    expect(find.textContaining('Roughly every 15 min each way'), findsOneWidget);
    expect(find.textContaining('(indicative)'), findsOneWidget,
        reason: 'a synthesised timetable must not read as a departure board');
    expect(find.textContaining('OpenStreetMap contributors'), findsOneWidget,
        reason: "credit the feed's declared producer, not the operator");
    expect(find.textContaining('separate ticket'), findsOneWidget);
  });

  testWidgets('a long walk is NOT called an interchange', (tester) async {
    await _pump(tester, _conn(distance: 1204));
    expect(find.textContaining('Interchange'), findsNothing,
        reason: 'calling a 1.2 km hike an interchange loses a rider\'s trust');
    expect(find.textContaining('1204m walk (about 16 min)'), findsOneWidget);
  });

  testWidgets('authoritative times drop the indicative caveat', (tester) async {
    final c = _conn()..['times_indicative'] = false;
    await _pump(tester, c);
    expect(find.textContaining('(indicative)'), findsNothing);
    expect(find.textContaining('community timetable'), findsNothing);
  });
}
