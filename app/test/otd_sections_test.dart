// Tests for the three DMRC Open Transit Data sections on station detail.
//
// The honesty-relevant behaviours are what get pinned:
//   * incomplete accessibility data reads "partly mapped", never a claim the
//     station is inaccessible — a dataset gap is not a missing lift;
//   * both ridership sections carry their data vintage (a dated snapshot
//     without its date is an overclaim);
//   * the busyness chart follows DMRC's hour convention (index 0 = 04:00);
//   * formatOtdPeriod never invents a date for shapes it can't parse.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/core/theme.dart';
import 'package:metropulse_app/features/station/station_detail_screen.dart';

Future<void> _pump(WidgetTester tester, Widget child) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: buildLightTheme(),
      home: Scaffold(body: SingleChildScrollView(child: child)),
    ),
  );
  await tester.pump();
}

void main() {
  group('formatOtdPeriod', () {
    test('formats a month and a range, passes junk through', () {
      expect(formatOtdPeriod('2025-01'), 'Jan 2025');
      expect(formatOtdPeriod('2024-09-01..2025-02-28'), 'Sep 2024 – Feb 2025');
      expect(formatOtdPeriod('unknown'), 'unknown');
    });
  });

  group('accessibility summary', () {
    testWidgets('complete station announces the step-free path', (tester) async {
      await _pump(
        tester,
        accessibilitySummaryForTest(const <String, dynamic>{
          'complete': true,
          'gates': [{'id': 'G1'}, {'id': 'G2'}],
          'lifts': [{'id': 'L1'}],
          'platforms': [{'id': 'P1'}],
        }),
      );
      expect(find.textContaining('Step-free path mapped'), findsOneWidget);
      expect(find.textContaining('2 gates · 1 lifts · 1 platforms'), findsOneWidget);
      expect(find.textContaining('DMRC station pathways data'), findsOneWidget);
    });

    testWidgets('incomplete data must say "partly mapped", not inaccessible',
        (tester) async {
      await _pump(
        tester,
        accessibilitySummaryForTest(const <String, dynamic>{
          'complete': false,
          'gates': [{'id': 'G1'}],
          'lifts': <Map<String, dynamic>>[],
          'platforms': [{'id': 'P1'}],
        }),
      );
      expect(find.textContaining('Partly mapped'), findsOneWidget);
      expect(find.textContaining('not accessible'), findsNothing,
          reason: 'A dataset gap must never be presented as a missing lift.');
      expect(find.textContaining('155370'), findsOneWidget,
          reason: 'When the map is incomplete, point to the DMRC helpline.');
    });
  });

  group('busyness chart', () {
    Map<String, dynamic> data() => <String, dynamic>{
          'period': '2024-09-01..2025-02-28',
          'profiles': {
            'weekday': {
              // Peak at index 14 -> 18:00 (6 PM).
              'entries': [for (var i = 0; i < 24; i++) i == 14 ? 900 : 100],
              'exits': [for (var i = 0; i < 24; i++) 100],
              'days': 130,
            },
          },
        };

    testWidgets('names the peak hour using the HR4 convention and the vintage',
        (tester) async {
      await _pump(tester, busynessChartForTest(data(), hourOverride: 9));
      expect(find.textContaining('busiest around 6 PM'), findsOneWidget,
          reason: 'index 14 + 4h offset = 18:00');
      expect(find.textContaining('Sep 2024 – Feb 2025'), findsOneWidget,
          reason: 'the snapshot period must be visible');
      expect(find.textContaining('Typical entries'), findsOneWidget,
          reason: 'these are typical values, and must not read as live');
    });

    testWidgets('renders nothing when the profile is empty', (tester) async {
      await _pump(
        tester,
        busynessChartForTest(const <String, dynamic>{
          'period': '2024-09-01..2025-02-28',
          'profiles': <String, dynamic>{},
        }),
      );
      expect(find.byType(Container), findsNothing);
    });
  });

  group('step-free gate matching', () {
    const access = <String, dynamic>{
      'step_free_gates': [
        {'id': 'st_x_gate_no_2', 'name': 'Gate No. 2'},
        {'id': 'st_x_gate_no_5', 'name': 'Gate No. 5'},
      ],
    };

    test('matches only on the exact gate number', () {
      expect(isStepFreeExitName('Chandni Chowk Metro Gate No. 2', access), isTrue);
      expect(isStepFreeExitName('Gate 5', access), isTrue,
          reason: 'name style differs between datasets; the number is the key');
      expect(isStepFreeExitName('Gate No. 3', access), isFalse);
    });

    test('no number on either side means no badge — never fuzzy-match', () {
      expect(isStepFreeExitName('Main Entrance', access), isFalse,
          reason: 'a wrong badge sends a wheelchair user to a staircase');
      expect(isStepFreeExitName('Gate No. 2', null), isFalse);
      expect(
        isStepFreeExitName('Gate No. 2', const <String, dynamic>{
          'step_free_gates': [{'id': 'g', 'name': 'Lift Entrance'}],
        }),
        isFalse,
      );
    });

    test('gate 12 must not match gate 1 or 2', () {
      expect(isStepFreeExitName('Gate No. 12', access), isFalse,
          reason: 'substring/prefix matching would badge the wrong gate');
    });
  });

  group('accessibility summary step-free gates', () {
    testWidgets('lists mapped step-free gates by name', (tester) async {
      await _pump(
        tester,
        accessibilitySummaryForTest(const <String, dynamic>{
          'complete': true,
          'gates': [{'id': 'g1'}, {'id': 'g2'}],
          'lifts': [{'id': 'l1'}],
          'platforms': [{'id': 'p1'}],
          'step_free_gates': [
            {'id': 'g1', 'name': 'Gate No. 1'},
            {'id': 'g2', 'name': 'Gate No. 4'},
          ],
        }),
      );
      expect(
        find.textContaining('Step-free path mapped from: Gate No. 1, Gate No. 4'),
        findsOneWidget,
      );
    });
  });

  group('top destinations', () {
    testWidgets('lists destinations with counts and the OD month', (tester) async {
      await _pump(
        tester,
        topDestinationsForTest(const <String, dynamic>{
          'period': '2025-01',
          'total_out': 944207,
          'top': [
            {'dest_stop_id': '47', 'dest_name': 'Chandni Chowk', 'count': 37177},
            {'dest_stop_id': '50', 'dest_name': 'Rajiv Chowk', 'count': 21050},
          ],
        }),
      );
      expect(find.text('Chandni Chowk'), findsOneWidget);
      expect(find.text('Rajiv Chowk'), findsOneWidget);
      expect(find.text('37.2k'), findsOneWidget);
      expect(find.textContaining('Jan 2025'), findsOneWidget);
      expect(find.textContaining('DMRC origin–destination data'), findsOneWidget);
    });
  });
}
