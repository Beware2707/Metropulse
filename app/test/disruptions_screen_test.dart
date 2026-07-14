// Locks in the Disruption Board with everything injected — no network, no
// offline bundle. Confirms the two sources render in separate sections
// (authoritative DMRC alerts vs unverified commuter reports), the unverified
// banner is present, the corroboration count shows, and the report form posts
// through the injected seam.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/models/station.dart';
import 'package:metropulse_app/features/disruptions/disruptions_providers.dart';
import 'package:metropulse_app/features/disruptions/disruptions_screen.dart';
import 'package:metropulse_app/features/home/home_providers.dart';
import 'package:metropulse_app/providers/core_providers.dart';

final _alerts = <Map<String, dynamic>>[
  {
    'severity': 'warning',
    'title': 'Yellow Line delays',
    'description': 'Trains running 8-10 min apart between Kashmere Gate and Central Secretariat.',
  },
];

final _reports = <Map<String, dynamic>>[
  {
    'id': 1,
    'stop_id': 'STN1',
    'route_id': null,
    'message': 'Trains held at the platform for over 10 minutes',
    'category': 'delay',
    'reported_at': DateTime.now().subtract(const Duration(minutes: 6)).toIso8601String(),
    'count': 3,
  },
  {
    'id': 2,
    'stop_id': null,
    'route_id': null,
    'message': 'Very crowded, could not board',
    'category': 'crowding',
    'reported_at': DateTime.now().subtract(const Duration(minutes: 2)).toIso8601String(),
    'count': 1,
  },
];

Widget _harness({
  List<Map<String, dynamic>> alerts = const [],
  List<Map<String, dynamic>> reports = const [],
  PostReportFn? postReport,
  PickStationFn? pickStation,
}) {
  return ProviderScope(
    overrides: [
      activeAlertsProvider.overrideWith((ref) async => alerts),
      riderReportsProvider.overrideWith((ref) async => reports),
      // Keep the station index off the offline bundle (which needs a store).
      stationIndexProvider.overrideWithValue(const <String, Station>{}),
    ],
    child: MaterialApp(
      home: DisruptionsScreen(postReport: postReport, pickStation: pickStation),
    ),
  );
}

void main() {
  testWidgets('renders both sections and the unverified banner', (tester) async {
    await tester.pumpWidget(_harness(alerts: _alerts, reports: _reports));
    await tester.pumpAndSettle();

    // The two section headers are clearly separated.
    expect(find.text('Official alerts'), findsOneWidget);
    expect(find.text('Reported by commuters'), findsOneWidget);

    // The honesty banner up top.
    expect(
      find.text('Commuter reports are unverified — official alerts come from DMRC.'),
      findsOneWidget,
    );

    // Official alert content.
    expect(find.text('Yellow Line delays'), findsOneWidget);

    // Rider report content + corroboration count + lone-report honesty.
    expect(find.text('Trains held at the platform for over 10 minutes'), findsOneWidget);
    expect(find.text('3 commuters reported this'), findsOneWidget);
    expect(find.text('reported by one commuter, unconfirmed'), findsOneWidget);
  });

  testWidgets('shows quiet copy for an empty section', (tester) async {
    await tester.pumpWidget(_harness(alerts: const [], reports: _reports));
    await tester.pumpAndSettle();

    expect(find.text('No service alerts from DMRC right now.'), findsOneWidget);
  });

  testWidgets('the report form posts through the injected seam', (tester) async {
    Map<String, dynamic>? captured;
    Future<bool> fakePost({String? stopId, String? routeId, required String message, String? category}) async {
      captured = {'stop_id': stopId, 'message': message, 'category': category};
      return true;
    }

    await tester.pumpWidget(_harness(reports: _reports, postReport: fakePost));
    await tester.pumpAndSettle();

    final reportButton = find.text('Report a delay');
    await tester.scrollUntilVisible(reportButton, 200, scrollable: find.byType(Scrollable).first);
    await tester.tap(reportButton);
    await tester.pumpAndSettle();

    // Choose a category and write a message.
    await tester.tap(find.text('Crowding'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'Platform packed, no room to board');
    await tester.pump();

    await tester.tap(find.text('Post report'));
    await tester.pumpAndSettle();

    expect(captured, isNotNull);
    expect(captured!['message'], 'Platform packed, no room to board');
    expect(captured!['category'], 'crowding');
    // Sheet closed and success SnackBar shown.
    expect(find.text('Post report'), findsNothing);
    expect(find.text('Thanks — your report is now visible to other commuters.'), findsOneWidget);
  });
}
