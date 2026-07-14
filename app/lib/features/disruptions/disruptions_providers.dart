import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../home/home_providers.dart' show alertsRepositoryProvider;

/// Recent rider-sourced disruption reports for the Disruption Board's
/// "Reported by commuters" section — community-sourced and unverified,
/// deliberately a separate provider from [activeAlertsProvider] (the
/// authoritative operator alerts) so the two are never conflated. Empty
/// offline or on error; the board then simply shows no commuter reports.
final riderReportsProvider = FutureProvider<List<Map<String, dynamic>>>(
  (ref) => ref.watch(alertsRepositoryProvider).riderReports(),
);
