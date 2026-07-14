// Locks in the fare-advisor card on the Commute Replay surface: with the
// fareAdvisorProvider overridden, it shows the estimate sentence and the
// API's note at trips > 0, and renders nothing at all at trips == 0 (an
// all-zero card would read as broken, not honest).
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/features/replay/fare_advisor_card.dart';

Widget _harness(Map<String, dynamic>? advisor) {
  return ProviderScope(
    overrides: [
      fareAdvisorProvider.overrideWith((ref) async => advisor),
    ],
    child: const MaterialApp(
      home: Scaffold(body: FareAdvisorCard()),
    ),
  );
}

void main() {
  testWidgets('renders the estimate sentence and note when trips > 0',
      (tester) async {
    await tester.pumpWidget(_harness({
      'window_days': 30,
      'trips': 42,
      'estimated_spend_inr': 1680,
      'card_saving_inr': 168,
      'offpeak_extra_saving_inr': 90,
      'note': 'Estimated from your completed trips against list fares.',
    }));
    await tester.pumpAndSettle();

    expect(
      find.text(
        'This month: 42 trips, about ₹1680. A smart card would have saved '
        'about ₹168 — off-peak riding another ₹90.',
      ),
      findsOneWidget,
    );
    expect(
      find.text('Estimated from your completed trips against list fares.'),
      findsOneWidget,
    );
  });

  testWidgets('renders nothing at trips == 0', (tester) async {
    await tester.pumpWidget(_harness({
      'window_days': 30,
      'trips': 0,
      'estimated_spend_inr': 0,
      'card_saving_inr': 0,
      'offpeak_extra_saving_inr': 0,
      'note': 'Take a few trips and we\'ll show what a card would save.',
    }));
    await tester.pumpAndSettle();

    expect(find.textContaining('This month:'), findsNothing);
    expect(find.byType(FareAdvisorCard), findsOneWidget);
  });

  testWidgets('renders nothing when the call did not land (null)',
      (tester) async {
    await tester.pumpWidget(_harness(null));
    await tester.pumpAndSettle();

    expect(find.textContaining('This month:'), findsNothing);
  });
}
