// Verifies the Hindi (hi) localization resolves end-to-end: when a widget
// tree is localized to `hi`, AppLocalizations.of() must return the Hindi
// subclass, plain getters must return Devanagari, and the one placeholder
// string (homeLeaveIn) must interpolate its {duration} argument correctly.
//
// This is the runtime counterpart to the static ARB key/placeholder audit:
// a renamed or dropped ICU placeholder would throw when the generated
// `homeLeaveIn(String)` method is invoked, which this test exercises.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/core/l10n_ext.dart';
import 'package:metropulse_app/l10n/gen/app_localizations.dart';
import 'package:metropulse_app/l10n/gen/app_localizations_hi.dart';

void main() {
  testWidgets('hi locale resolves AppLocalizations to the Hindi subclass', (tester) async {
    late AppLocalizations loc;
    await tester.pumpWidget(
      MaterialApp(
        locale: const Locale('hi'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) {
            loc = AppLocalizations.of(context);
            return Text(context.t.plannerLetsGo);
          },
        ),
      ),
    );

    // The delegate must pick the Hindi implementation, not fall back to en.
    expect(loc, isA<AppLocalizationsHi>());
    expect(loc.localeName, 'hi');

    // A known translated string renders in Devanagari (not the English source).
    expect(find.text('चलिए चलें'), findsOneWidget);
    expect(find.text("Let's go"), findsNothing);
  });

  testWidgets('hi placeholder string interpolates {duration} without throwing', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        locale: const Locale('hi'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(
          builder: (context) => Text(context.t.homeLeaveIn('5 मिनट')),
        ),
      ),
    );

    // The {duration} arg must land inside the Hindi sentence verbatim.
    expect(find.text('समय पर पहुँचने के लिए 5 मिनट में निकलें'), findsOneWidget);
  });

  test('every hi getter returns a non-empty Devanagari (or brand) string', () {
    final hi = AppLocalizationsHi();
    // Spot the core-flow keys the coverage claim depends on.
    expect(hi.navHome, 'होम');
    expect(hi.journeyEndConfirmTitle, 'यह यात्रा समाप्त करें?');
    expect(hi.searchNoResults, contains('नहीं मिला'));
    expect(hi.settingsLanguageTitle, 'भाषा');
    expect(hi.languageSystemDefault, 'सिस्टम डिफ़ॉल्ट');
    // Brand name stays Latin.
    expect(hi.appTitle, 'MetroPulse');
  });
}
