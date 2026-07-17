import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/features/station/station_detail_screen.dart';

Future<void> _pump(WidgetTester tester, Map<String, dynamic> exit) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(body: exitLandmarksForTest(exit)),
    ),
  );
}

void main() {
  testWidgets('flags a tourist landmark with an attraction icon', (tester) async {
    await _pump(tester, {
      'name': 'Gate 5',
      'landmarks': ['Red Fort', 'HDFC Bank'],
      'landmarks_detail': [
        {'name': 'Red Fort', 'category': 'monument', 'tourist': true},
        {'name': 'HDFC Bank', 'category': 'bank', 'tourist': false},
      ],
    });
    expect(find.text('Red Fort'), findsOneWidget);
    expect(find.text('HDFC Bank'), findsOneWidget);
    // the tourist place gets the attraction marker; the bank does not
    expect(find.byIcon(Icons.attractions_rounded), findsOneWidget);
  });

  testWidgets('falls back to the flat landmarks string when no detail', (tester) async {
    await _pump(tester, {
      'name': 'Gate 1',
      'landmarks': ['City Mall', 'Bus Stand'],
    });
    expect(find.text('City Mall, Bus Stand'), findsOneWidget);
    expect(find.byIcon(Icons.attractions_rounded), findsNothing);
  });

  testWidgets('renders nothing when there are no landmarks', (tester) async {
    await _pump(tester, {'name': 'Gate 2', 'landmarks': <String>[]});
    expect(find.byIcon(Icons.attractions_rounded), findsNothing);
    expect(find.byType(Text), findsNothing);
  });
}
