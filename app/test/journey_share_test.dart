// Locks in the share-my-live-journey control with every backend call and the
// location fix injected — no network, no geolocator. Confirms: the button
// starts a share and reveals the link with its honest disclosure; the device
// position is posted; the visible Stop affordance calls stopSharing; a failed
// share is honest; and a location denial stops sharing on its own.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/data/location_service.dart';
import 'package:metropulse_app/features/journey_mode/journey_share.dart';

Widget _harness({
  required ShareJourneyFn shareJourney,
  PostPositionFn? postPosition,
  StopSharingFn? stopSharing,
  ResolvePositionFn? resolvePosition,
}) {
  return ProviderScope(
    child: MaterialApp(
      home: Scaffold(
        body: JourneyShareButton(
          journeyId: 42,
          shareJourney: shareJourney,
          postPosition: postPosition ?? (_, __, ___) async {},
          stopSharing: stopSharing ?? (_) async {},
          resolvePosition: resolvePosition ?? () async => const LocationFix(28.6, 77.0),
          copyToClipboard: (_) async {},
          launchExternal: (_) async => true,
          // Long interval so exactly the immediate push runs during the test;
          // Stop cancels the timer before the test ends.
          positionInterval: const Duration(minutes: 5),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('starts sharing, posts position, reveals link, and Stop stops', (tester) async {
    var shareCalls = 0;
    final positions = <(double, double)>[];
    var stopCalls = 0;

    await tester.pumpWidget(_harness(
      shareJourney: (id) async {
        shareCalls++;
        return {
          'token': 'abc123',
          'share_url': 'https://metropulse.app/s/abc123',
          'expires_at': DateTime.now().add(const Duration(hours: 2)).toIso8601String(),
        };
      },
      postPosition: (id, lat, lon) async => positions.add((lat, lon)),
      stopSharing: (id) async => stopCalls++,
    ));

    expect(find.text('Share my trip'), findsOneWidget);

    await tester.tap(find.text('Share my trip'));
    await tester.pumpAndSettle();

    // Share created, position posted immediately, link sheet shown with the
    // honest disclosure and copy affordance.
    expect(shareCalls, 1);
    expect(positions, [(28.6, 77.0)]);
    expect(
      find.text('Anyone with the link can see your live location until you arrive or stop sharing.'),
      findsWidgets,
    );
    expect(find.text('Copy link'), findsOneWidget);
    expect(find.text('https://metropulse.app/s/abc123'), findsOneWidget);

    // Dismiss the link sheet by tapping the scrim.
    await tester.tapAt(const Offset(20, 20));
    await tester.pumpAndSettle();

    // The persistent "You're sharing" banner with a visible Stop.
    expect(find.text("You're sharing this trip"), findsOneWidget);
    expect(find.text('Stop'), findsOneWidget);

    await tester.tap(find.text('Stop'));
    await tester.pumpAndSettle();

    expect(stopCalls, 1);
    expect(find.text("You're sharing this trip"), findsNothing);
    expect(find.text('Share my trip'), findsOneWidget);
  });

  testWidgets('a failed share is honest and does not enter sharing state', (tester) async {
    await tester.pumpWidget(_harness(shareJourney: (id) async => null));

    await tester.tap(find.text('Share my trip'));
    await tester.pumpAndSettle();

    expect(find.text("Couldn't start sharing — check your connection and try again."), findsOneWidget);
    expect(find.text("You're sharing this trip"), findsNothing);
    expect(find.text('Share my trip'), findsOneWidget);
  });

  testWidgets('location denial stops sharing on its own', (tester) async {
    var stopCalls = 0;
    await tester.pumpWidget(_harness(
      shareJourney: (id) async => {
        'token': 't',
        'share_url': 'https://metropulse.app/s/t',
        'expires_at': DateTime.now().toIso8601String(),
      },
      resolvePosition: () async => const LocationDenied(permanently: false),
      stopSharing: (id) async => stopCalls++,
    ));

    await tester.tap(find.text('Share my trip'));
    await tester.pumpAndSettle();

    expect(stopCalls, 1);
    expect(find.text('Location is off, so we stopped sharing your live trip.'), findsOneWidget);
    expect(find.text("You're sharing this trip"), findsNothing);
  });
}
