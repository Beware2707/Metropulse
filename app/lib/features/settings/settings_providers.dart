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

final notificationsEnabledProvider =
    Provider<bool>((ref) => ref.watch(localStoreProvider).notificationsEnabled);
