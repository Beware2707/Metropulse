// HelpScreen surfaces DMRC's real, published rider contacts and honest
// lost-property guidance. It must show the two verified helpline numbers,
// carry the "held about 3 months, no fee" wording, cite the source honestly,
// and dial via `tel:` through the injected launcher (a real call needs a host
// platform, so only the hand-off target is asserted).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/features/help/help_screen.dart';

void main() {
  Future<List<Uri>> pumpHelp(WidgetTester tester,
      {bool launchSucceeds = true}) async {
    final launched = <Uri>[];
    await tester.pumpWidget(
      MaterialApp(
        home: HelpScreen(
          launchExternal: (uri) async {
            launched.add(uri);
            return launchSucceeds;
          },
        ),
      ),
    );
    return launched;
  }

  testWidgets('renders both real DMRC numbers, the lost-property terms and the source', (tester) async {
    await pumpHelp(tester);

    // The two verified DMRC helpline numbers.
    expect(dmrcHelplineNumber, '155370');
    expect(dmrcSecurityNumber, '155655');
    expect(find.textContaining('155370'), findsWidgets);
    expect(find.textContaining('155655'), findsWidgets);

    expect(find.text('DMRC helpline (24/7)'), findsOneWidget);
    expect(find.text('Security / CISF helpline'), findsOneWidget);

    // Honest lost-property terms: ~3 months, no fee.
    expect(find.textContaining('held about 3 months'), findsOneWidget);
    expect(find.textContaining('no fee to claim'), findsOneWidget);

    // Source cited honestly.
    expect(find.textContaining('DMRC published contacts'), findsOneWidget);
  });

  testWidgets('tapping the helpline dials it via tel: through the launcher', (tester) async {
    final launched = await pumpHelp(tester);

    await tester.tap(find.text('DMRC helpline (24/7)'));
    await tester.pump();

    expect(launched, [Uri(scheme: 'tel', path: '155370')]);
  });

  testWidgets('tapping the security row dials the CISF number', (tester) async {
    final launched = await pumpHelp(tester);

    await tester.tap(find.text('Security / CISF helpline'));
    await tester.pump();

    expect(launched, [Uri(scheme: 'tel', path: '155655')]);
  });

  testWidgets('shows a SnackBar when the dialler cannot be opened', (tester) async {
    await pumpHelp(tester, launchSucceeds: false);

    await tester.tap(find.text('DMRC helpline (24/7)'));
    await tester.pump();

    expect(find.byType(SnackBar), findsOneWidget);
  });
}
