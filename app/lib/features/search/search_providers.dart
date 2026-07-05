import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/core_providers.dart';
import '../home/home_providers.dart';

/// Stop ids of the user's favourite stations, for search-result boosting.
final favouriteStopIdsProvider = Provider<Set<String>>((ref) {
  final favourites = ref.watch(favouriteStationsProvider).valueOrNull ?? const [];
  return {for (final row in favourites) '${row['stop_id']}'};
});

/// Recently visited/searched stop ids, most-recent-first.
final recentSearchIdsProvider = Provider<List<String>>(
  (ref) => ref.watch(localStoreProvider).recentSearchStopIds,
);
