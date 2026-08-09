// The Journey Mode guidance card.
//
// This is read while walking, often underground, often carrying something —
// so it is one line of action plus one line of evidence, and its colour
// carries meaning: green only for a confirmed step-free path, amber for
// "not mapped" (a caution, never a verdict on the station).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/core/design/app_colors.dart';
import 'package:metropulse_app/core/theme.dart';
import 'package:metropulse_app/domain/station_guidance.dart';
import 'package:metropulse_app/features/journey_mode/journey_mode_screen.dart';

Future<void> _pump(WidgetTester tester, StationGuidance g) async {
  await tester.pumpWidget(MaterialApp(
    theme: buildLightTheme(),
    home: Scaffold(body: stationGuidanceCardForTest(g)),
  ));
  await tester.pump();
}

void main() {
  testWidgets('a confirmed step-free gate is green and uses the accessible icon',
      (tester) async {
    await _pump(tester, const StationGuidance(
      headline: 'Leave by Gate No. 2',
      liftNote: 'Lift to the platform',
      stepFree: true,
    ));
    expect(find.text('Leave by Gate No. 2'), findsOneWidget);
    final icon = tester.widget<Icon>(find.byType(Icon).first);
    expect(icon.icon, Icons.accessible_rounded);
    expect(icon.color, AppColors.live);
  });

  testWidgets('unmapped is amber and informational, never red', (tester) async {
    await _pump(tester, const StationGuidance(
      headline: 'Step-free exit not mapped here',
      landmarkNote: 'Call DMRC on 155370 to check lift service',
      stepFreeUnmapped: true,
    ));
    final icon = tester.widget<Icon>(find.byType(Icon).first);
    expect(icon.color, AppColors.warning,
        reason: 'the station may be accessible and merely unmapped');
    expect(icon.color, isNot(AppColors.danger));
    expect(icon.icon, Icons.info_outline_rounded);
  });

  testWidgets('an ordinary gate shows a door, not an accessibility claim',
      (tester) async {
    await _pump(tester, const StationGuidance(
      headline: 'Enter at Gate No. 1',
      landmarkNote: 'Near Red Fort',
    ));
    final icon = tester.widget<Icon>(find.byType(Icon).first);
    expect(icon.icon, Icons.door_front_door_rounded);
    expect(icon.color, isNot(AppColors.live),
        reason: 'green would imply a step-free path we have not confirmed');
  });

  testWidgets('the tick is only shown on a graph-confirmed lift path',
      (tester) async {
    await _pump(tester, const StationGuidance(
      headline: 'Leave by Gate No. 9',
      liftNote: '2 lifts at this station — path from this gate not mapped',
    ));
    expect(find.byIcon(Icons.check_circle_rounded), findsNothing,
        reason: 'the tick is a promise; this is only a fact about the station');
    expect(find.byIcon(Icons.elevator_outlined), findsOneWidget);
  });

  testWidgets('a confirmed path does get the tick', (tester) async {
    await _pump(tester, const StationGuidance(
      headline: 'Leave by Gate No. 2',
      liftNote: 'Lift to the platform',
      stepFree: true,
    ));
    expect(find.byIcon(Icons.check_circle_rounded), findsOneWidget);
  });

  testWidgets('renders without a detail line', (tester) async {
    await _pump(tester, const StationGuidance(headline: 'Leave by Gate No. 3'));
    expect(find.text('Leave by Gate No. 3'), findsOneWidget);
  });
}
