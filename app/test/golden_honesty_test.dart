// Golden tests for the surfaces where real, shipped bugs were found by
// looking at a device — bugs that a green analyzer, mypy-strict backend and
// 600+ passing tests all missed:
//
//   1. LiveIndicator claimed a green "LIVE" over schedule-interpolated data.
//      This is the honesty guard: if the pill ever says LIVE when the data is
//      estimated, these goldens fail.
//   2. GhostButton(expand: false) silently stretched to full width, making
//      onboarding's "Skip" the most prominent control on the screen.
//   3. Exit landmarks must visibly distinguish a tourist place from a bank.
//
// Run `flutter test --update-goldens` to re-baseline after an intentional
// visual change; a diff you did NOT intend is the point of these files.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/core/theme.dart';
import 'package:metropulse_app/core/widgets/gradient_button.dart';
import 'package:metropulse_app/core/widgets/live_indicator.dart';
import 'package:metropulse_app/data/ws_client.dart';
import 'package:metropulse_app/features/station/station_detail_screen.dart';
import 'package:metropulse_app/providers/live_providers.dart';

/// The captured region. Matching on this key rather than on the widget's own
/// type keeps the golden stable when the widget's internals are refactored,
/// and avoids `find.byType(SizedBox).first` picking up framework internals.
const _target = ValueKey('golden-target');

/// The LiveIndicator's dot pulses forever, so [WidgetTester.pumpAndSettle]
/// would spin until it times out. Advancing the (fake) clock by exactly one
/// full pulse instead lands the controller at 1.0 — dot at full opacity —
/// which is both deterministic and the phase worth looking at.
const _onePulse = Duration(milliseconds: 1200);

/// Renders [child] on the app's real theme at a fixed size, so a golden diff
/// means the widget changed — not the harness.
Future<void> _pumpGolden(
  WidgetTester tester,
  Widget child, {
  Size size = const Size(360, 120),
  List<Override> overrides = const [],
  Duration? pumpFor,
}) async {
  await tester.binding.setSurfaceSize(size);
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    ProviderScope(
      overrides: overrides,
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: buildLightTheme(),
        home: Scaffold(
          body: Center(child: RepaintBoundary(key: _target, child: child)),
        ),
      ),
    ),
  );
  if (pumpFor != null) {
    await tester.pump(pumpFor);
  } else {
    await tester.pumpAndSettle();
  }
}

/// Pins the websocket status the LiveIndicator reads.
Override _ws(WsStatus status) =>
    wsStatusProvider.overrideWith((ref) => Stream.value(status));

void main() {
  group('LiveIndicator — the honesty guard', () {
    testWidgets('connected + real GPS data shows LIVE', (tester) async {
      await _pumpGolden(
        tester,
        const LiveIndicator(dataEstimated: false),
        size: const Size(200, 80),
        overrides: [_ws(WsStatus.live)],
        pumpFor: _onePulse,
      );
      await expectLater(
        find.byKey(_target),
        matchesGoldenFile('goldens/live_indicator_live.png'),
      );
    });

    testWidgets('connected but SCHEDULE-estimated data must NOT say LIVE',
        (tester) async {
      await _pumpGolden(
        tester,
        const LiveIndicator(dataEstimated: true),
        size: const Size(200, 80),
        overrides: [_ws(WsStatus.live)],
        pumpFor: _onePulse,
      );
      await expectLater(
        find.byKey(_target),
        matchesGoldenFile('goldens/live_indicator_schedule.png'),
      );
    });

    testWidgets('reconnecting', (tester) async {
      await _pumpGolden(
        tester,
        // Explicitly estimated — the honest value while no realtime feed
        // exists. This previously leaned on a `dataEstimated = false` default,
        // i.e. the honesty golden was itself asserting the un-honest default.
        // RECONNECTING renders the same either way, so the golden is unchanged.
        const LiveIndicator(dataEstimated: true),
        size: const Size(240, 80),
        overrides: [_ws(WsStatus.reconnecting)],
        pumpFor: _onePulse,
      );
      await expectLater(
        find.byKey(_target),
        matchesGoldenFile('goldens/live_indicator_reconnecting.png'),
      );
    });
  });

  group('GhostButton — the sizing guard', () {
    testWidgets('expand:false hugs its label (must not fill the width)',
        (tester) async {
      await _pumpGolden(
        tester,
        // Loose constraints — the exact situation that used to stretch it.
        const Align(
          alignment: Alignment.topRight,
          child: GhostButton(label: 'Skip'),
        ),
        size: const Size(360, 120),
      );
      await expectLater(
        find.byKey(_target),
        matchesGoldenFile('goldens/ghost_button_compact.png'),
      );
    });

    testWidgets('expand:true fills deliberately', (tester) async {
      await _pumpGolden(
        tester,
        const SizedBox(
          width: 320,
          child: GhostButton(label: 'View on network map', expand: true),
        ),
        size: const Size(360, 120),
      );
      await expectLater(
        find.byKey(_target),
        matchesGoldenFile('goldens/ghost_button_expanded.png'),
      );
    });
  });

  group('Exit landmarks', () {
    testWidgets('tourist places are visibly marked, ordinary ones are not',
        (tester) async {
      await _pumpGolden(
        tester,
        SizedBox(
          width: 320,
          child: exitLandmarksForTest(const <String, dynamic>{
            'name': 'Chandni Chowk Metro Gate No. 3',
            'landmarks': ['Gandhi Statue', 'Delhi Town Hall'],
            'landmarks_detail': [
              {'name': 'Gandhi Statue', 'category': 'monument', 'tourist': true},
              {'name': 'Delhi Town Hall', 'category': 'townhall', 'tourist': false},
            ],
          }),
        ),
        size: const Size(360, 140),
      );
      await expectLater(
        find.byKey(_target),
        matchesGoldenFile('goldens/exit_landmarks_tourist.png'),
      );
    });
  });
}
