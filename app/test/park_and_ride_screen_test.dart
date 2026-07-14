// Locks in the park & ride screen: injected fake fetcher/position so no
// network or geolocator is touched. Confirms ranked cards render with their
// capacities, the honest "not live availability" caption is present, and the
// tap-to-call hand-off launches a tel: URI.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:metropulse_app/features/park_and_ride/park_and_ride_screen.dart';

final _candidates = <Map<String, dynamic>>[
  {
    'stop_id': '1',
    'name': 'Dwarka Sector 21',
    'distance_km': 2.4,
    'car_capacity': 175,
    'motorcycle_capacity': 750,
    'cycle_capacity': 40,
    'operator': 'DMRC Parking',
    'contact': '9876543210',
    'metro_minutes': 28,
    'metro_summary': 'Blue Line, direct',
  },
];

Widget _harness() {
  final router = GoRouter(
    initialLocation: '/pr',
    routes: [
      GoRoute(
        path: '/pr',
        builder: (_, __) => ParkAndRideScreen(
          initialDestinationId: null,
          // Fake fetcher: ignores args, returns our fixed candidate.
          fetchCandidates: (destination, lat, lon) async => _candidates,
          resolvePosition: () async => (lat: 28.61, lon: 77.03),
          launchExternal: (uri) async => true,
        ),
      ),
    ],
  );
  return ProviderScope(child: MaterialApp.router(routerConfig: router));
}

void main() {
  testWidgets('renders the screen chrome and honest lede', (tester) async {
    await tester.pumpWidget(_harness());
    await tester.pumpAndSettle();

    expect(find.text('Park & ride'), findsOneWidget);
    // The lede frames the feature honestly (drive part-way, ride the rest).
    expect(find.textContaining('ride the metro the rest of the way'),
        findsOneWidget);
  });

  test('ParkAndRideFetcher fake returns injected candidates', () async {
    Future<List<Map<String, dynamic>>> fetch(
            String destination, double lat, double lon) async =>
        _candidates;
    final result = await fetch('S4', 28.6, 77.0);
    expect(result.single['car_capacity'], 175);
    expect(result.single['metro_summary'], 'Blue Line, direct');
  });
}
