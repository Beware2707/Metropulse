import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/core_providers.dart';

/// Reactive wrappers around Hive-backed settings.
///
/// `localStoreProvider` is a fixed value-override (see main.dart), so it
/// never re-runs on `ref.invalidate` — each setting therefore gets its own
/// thin `Provider` that re-reads Hive on invalidate, which IS a real
/// recomputation, so widgets watching it rebuild correctly after a write.
final apiBaseProvider = Provider<String>((ref) => ref.watch(localStoreProvider).apiBase);

final textScaleFactorProvider =
    Provider<double>((ref) => ref.watch(localStoreProvider).textScaleFactor);

final highContrastProvider =
    Provider<bool>((ref) => ref.watch(localStoreProvider).highContrast);

final dynamicColorEnabledProvider =
    Provider<bool>((ref) => ref.watch(localStoreProvider).dynamicColorEnabled);

/// Whether the rider needs step-free (lift-served) routes. Read by the
/// planner AND by Journey Mode, so the need is stated once and then honoured
/// at the moment it matters — standing in the station.
final stepFreePreferredProvider =
    Provider<bool>((ref) => ref.watch(localStoreProvider).stepFreePreferred);

final notificationsEnabledProvider =
    Provider<bool>((ref) => ref.watch(localStoreProvider).notificationsEnabled);

/// Whether the rider agreed to share anonymous usage analytics. Default false
/// — see [LocalStore.analyticsConsent] for why the default direction matters.
final analyticsConsentProvider =
    Provider<bool>((ref) => ref.watch(localStoreProvider).analyticsConsent);

final analyticsConsentAskedProvider =
    Provider<bool>((ref) => ref.watch(localStoreProvider).analyticsConsentAsked);

/// Whether the rider agreed to contribute station knowledge. Separate from
/// analytics consent on purpose — see [LocalStore.contributionConsent].
final contributionConsentProvider =
    Provider<bool>((ref) => ref.watch(localStoreProvider).contributionConsent);

final contributionConsentAskedProvider = Provider<bool>(
    (ref) => ref.watch(localStoreProvider).contributionConsentAsked);
