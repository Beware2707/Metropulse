// Locks in the meet-in-the-middle screen: an injected fake fetcher plus
// pre-selected starting stations so no network or station bundle is touched.
// Confirms both travel times render, the backend's fairness order is
// preserved, and the friendly empty state shows when there's no fair meeting
// point.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:metropulse_app/domain/models/station.dart';
import 'package:metropulse_app/features/meet/meet_screen.dart';

const _you = Station(stopId: 'A', name: 'Rajiv Chowk', lat: 28.63, lon: 77.22);
const _friend =
    Station(stopId: 'B', name: 'Hauz Khas', lat: 28.54, lon: 77.20);

// Fairness-first order, exactly as the API returns it: max_minutes asc, then
// total asc. The card must not re-sort.
final _candidates = <Map<String, dynamic>>[
  {
    'stop_id': 'M1',
    'name': 'INA',
    'minutes_a': 12,
    'minutes_b': 10,
    'max_minutes': 12,
    'total_minutes': 22,
  },
  {
    'stop_id': 'M2',
    'name': 'AIIMS',
    'minutes_a': 15,
    'minutes_b': 8,
    'max_minutes': 15,
    'total_minutes': 23,
  },
];

Widget _harness({
  required MeetFetcher fetcher,
  Station? you = _you,
  Station? friend = _friend,
}) {
  final router = GoRouter(
    initialLocation: '/meet',
    routes: [
      GoRoute(
        path: '/meet',
        builder: (_, __) => MeetScreen(
          fetchCandidates: fetcher,
          initialYou: you,
          initialFriend: friend,
        ),
      ),
      GoRoute(
        path: '/station/:stopId',
        builder: (_, state) =>
            Scaffold(body: Text('Station ${state.pathParameters['stopId']}')),
      ),
    ],
  );
  return ProviderScope(child: MaterialApp.router(routerConfig: router));
}

void main() {
  testWidgets('renders both travel times for each candidate', (tester) async {
    await tester.pumpWidget(
      _harness(fetcher: (a, b) async => _candidates),
    );
    await tester.pumpAndSettle();

    expect(find.text('INA'), findsOneWidget);
    expect(find.text('AIIMS'), findsOneWidget);
    // Both sides shown, honestly labelled per candidate.
    expect(find.text('You: 12 min · Them: 10 min'), findsOneWidget);
    expect(find.text('You: 15 min · Them: 8 min'), findsOneWidget);
  });

  testWidgets('preserves the fairness order the API returned', (tester) async {
    await tester.pumpWidget(
      _harness(fetcher: (a, b) async => _candidates),
    );
    await tester.pumpAndSettle();

    final ina = tester.getTopLeft(find.text('INA')).dy;
    final aiims = tester.getTopLeft(find.text('AIIMS')).dy;
    // INA (max_minutes 12) must sit above AIIMS (max_minutes 15).
    expect(ina, lessThan(aiims));
  });

  testWidgets('passes the chosen stops through to the fetcher', (tester) async {
    String? seenA;
    String? seenB;
    await tester.pumpWidget(
      _harness(fetcher: (a, b) async {
        seenA = a;
        seenB = b;
        return _candidates;
      }),
    );
    await tester.pumpAndSettle();

    expect(seenA, 'A');
    expect(seenB, 'B');
  });

  testWidgets('shows a friendly empty state when there are no candidates',
      (tester) async {
    await tester.pumpWidget(
      _harness(fetcher: (a, b) async => const []),
    );
    await tester.pumpAndSettle();

    expect(
      find.textContaining("couldn't find a fair meeting point"),
      findsOneWidget,
    );
    expect(find.text('INA'), findsNothing);
  });
}
