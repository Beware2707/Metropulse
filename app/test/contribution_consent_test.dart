// Contribution consent is a separate decision from analytics consent, and the
// storage layer has to keep it that way.
//
// This matters more than it looks. The privacy policy tells riders that the
// analytics toggle does NOT receive which stations they travelled between — and
// a coach-exit report is exactly that, about one named station. If the two
// consents were ever wired to the same key, turning on analytics would silently
// opt someone into the thing they were promised it excluded.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:metropulse_app/data/local_store.dart';

void main() {
  late Directory tempDir;
  late LocalStore store;

  setUpAll(() async {
    tempDir = Directory.systemTemp.createTempSync('mp_consent_test');
    Hive.init(tempDir.path);
    store = await LocalStore.open();
  });

  tearDownAll(() async {
    await Hive.close();
    tempDir.deleteSync(recursive: true);
  });

  setUp(() async {
    await store.setAnalyticsConsent(false);
    await store.setContributionConsent(false);
    await store.setContributionConsentAsked(false);
  });

  test('a fresh install has agreed to neither', () async {
    final fresh = Directory.systemTemp.createTempSync('mp_consent_fresh');
    addTearDown(() => fresh.deleteSync(recursive: true));
    // The defaults are read from an absent key, which is the case that matters:
    // `== 'true'` means missing resolves to no.
    expect(store.contributionConsent, isFalse);
    expect(store.contributionConsentAsked, isFalse);
    expect(store.analyticsConsent, isFalse);
  });

  test('turning on analytics does not turn on contributions', () async {
    await store.setAnalyticsConsent(true);

    expect(store.analyticsConsent, isTrue);
    expect(store.contributionConsent, isFalse,
        reason: 'the policy promises analytics excludes where you travelled; '
            'a coach-exit report is exactly that and needs its own yes');
  });

  test('turning on contributions does not turn on analytics', () async {
    await store.setContributionConsent(true);

    expect(store.contributionConsent, isTrue);
    expect(store.analyticsConsent, isFalse);
  });

  test('each can be withdrawn without touching the other', () async {
    await store.setAnalyticsConsent(true);
    await store.setContributionConsent(true);

    await store.setContributionConsent(false);
    expect(store.contributionConsent, isFalse);
    expect(store.analyticsConsent, isTrue, reason: 'independent decisions');
  });

  test('"asked" is tracked separately from "agreed"', () async {
    // So a rider who said no once is not nagged forever, and one who has never
    // been asked can still be offered the choice.
    await store.setContributionConsentAsked(true);

    expect(store.contributionConsentAsked, isTrue);
    expect(store.contributionConsent, isFalse,
        reason: 'being asked is not agreeing');
  });
}
