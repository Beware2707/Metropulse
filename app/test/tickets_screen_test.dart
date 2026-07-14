// TicketsScreen is a hand-off surface, not a store: it must honestly say
// MetroPulse never handles money, list DMRC's five official channels, and
// carry the AVM-sync caveat for online card recharge. Actual URL launching
// needs a host platform, so the launcher is injected through the screen's
// test seam and only the hand-off targets are asserted.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/core/config.dart';
import 'package:metropulse_app/features/tickets/tickets_screen.dart';

void main() {
  Future<List<Uri>> pumpTickets(WidgetTester tester, {bool launchSucceeds = true}) async {
    final launched = <Uri>[];
    await tester.pumpWidget(
      MaterialApp(
        home: TicketsScreen(
          launchExternal: (uri) async {
            launched.add(uri);
            return launchSucceeds;
          },
        ),
      ),
    );
    return launched;
  }

  testWidgets('renders the honesty lede and all five official channel rows', (tester) async {
    await pumpTickets(tester);

    expect(
      find.textContaining('MetroPulse never handles your money'),
      findsOneWidget,
    );

    expect(find.text('WhatsApp ticketing'), findsOneWidget);
    expect(find.text('DMRC web ticket portal'), findsOneWidget);
    expect(find.text('DMRC Momentum 2.0 app'), findsOneWidget);
    expect(find.text('Official online recharge'), findsOneWidget);
    expect(find.text('Autope auto top-up'), findsOneWidget);

    // The honest AVM caveat: an online top-up isn't usable until the card is
    // tapped on a station Add Value Machine.
    expect(
      find.textContaining('tap your card on any station AVM'),
      findsOneWidget,
    );
  });

  testWidgets('each row hands off to its official channel URL', (tester) async {
    final launched = await pumpTickets(tester);

    for (final (title, url) in [
      ('WhatsApp ticketing', AppConfig.dmrcWhatsAppTicketsUrl),
      ('DMRC web ticket portal', AppConfig.dmrcQrPortalUrl),
      ('DMRC Momentum 2.0 app', AppConfig.dmrcMomentumStoreUrl),
      ('Official online recharge', AppConfig.dmrcCardRechargeUrl),
      ('Autope auto top-up', AppConfig.autopeUrl),
    ]) {
      launched.clear();
      await tester.ensureVisible(find.text(title));
      await tester.tap(find.text(title));
      await tester.pump();
      expect(launched, [Uri.parse(url)], reason: '$title should open $url');
    }
  });

  testWidgets('shows a SnackBar when a channel fails to open', (tester) async {
    await pumpTickets(tester, launchSucceeds: false);

    await tester.ensureVisible(find.text('WhatsApp ticketing'));
    await tester.tap(find.text('WhatsApp ticketing'));
    await tester.pump();

    expect(find.byType(SnackBar), findsOneWidget);
  });
}
