import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/design/app_spacing.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/station_row.dart';
import '../../domain/models/station.dart';
import '../../domain/search_index.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart' show commutePredictionProvider;
import '../search/search_providers.dart';

/// A modal station picker shared by the Journey Planner and anywhere else
/// that needs one: offline search over stations + curated aliases +
/// curated exit landmarks, boosted by favourites/recents, with Recent /
/// Favourite quick-pick rows when the query is empty.
class StationSearchSheet extends ConsumerStatefulWidget {
  const StationSearchSheet({super.key, this.title = 'Where to?', required this.isOrigin});

  final String title;

  /// Which endpoint this picker is filling in — used only to decide which
  /// side of the user's predicted commute ("Your usual") to suggest.
  final bool isOrigin;

  @override
  ConsumerState<StationSearchSheet> createState() => _StationSearchSheetState();
}

class _StationSearchSheetState extends ConsumerState<StationSearchSheet> {
  String _query = '';
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bundleAsync = ref.watch(offlineBundleProvider);
    final bundle = bundleAsync.valueOrNull;
    final stations = bundle?.stations ?? const <Station>[];
    final exits = bundle?.exits ?? const <String, List<StationExitInfo>>{};
    final favouriteIds = ref.watch(favouriteStopIdsProvider);
    final recentIds = ref.watch(recentSearchIdsProvider);
    final byId = {for (final s in stations) s.stopId: s};

    final trimmed = _query.trim();
    final hits = trimmed.isEmpty
        ? const <SearchHit>[]
        : rankWithBoosts(
            searchStations(stations: stations, exits: exits, query: trimmed),
            favouriteStopIds: favouriteIds,
            recentStopIds: recentIds.toSet(),
          );

    return Padding(
      padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SizedBox(
        height: MediaQuery.of(context).size.height * 0.85,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, AppSpacing.sm),
              child: TextField(
                controller: _controller,
                autofocus: true,
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.search_rounded),
                  hintText: widget.title,
                  suffixIcon: _query.isEmpty
                      ? null
                      : IconButton(
                          icon: const Icon(Icons.close_rounded),
                          onPressed: () {
                            _controller.clear();
                            setState(() => _query = '');
                          },
                        ),
                ),
                onChanged: (value) => setState(() => _query = value),
              ),
            ),
            Expanded(
              child: bundleAsync.isLoading && stations.isEmpty
                  ? const Center(child: CircularProgressIndicator())
                  : trimmed.isEmpty
                      ? _QuickPicks(
                          favouriteIds: favouriteIds,
                          recentIds: recentIds,
                          byId: byId,
                          isOrigin: widget.isOrigin,
                          onPick: _pick,
                        )
                      : hits.isEmpty
                          ? const Center(
                              child: Padding(
                                padding: EdgeInsets.all(AppSpacing.xxl),
                                child: EmptyState(
                                  icon: Icons.search_off_rounded,
                                  message: "We couldn't find that one — try a different name or landmark.",
                                  compact: true,
                                ),
                              ),
                            )
                          : ListView(
                              padding: const EdgeInsets.fromLTRB(AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.xxl),
                              children: [
                                for (final hit in hits)
                                  StationRow(
                                    station: hit.station,
                                    icon: switch (hit.reason) {
                                      SearchMatchReason.alias => Icons.label_outline_rounded,
                                      SearchMatchReason.landmark => Icons.near_me_rounded,
                                      SearchMatchReason.name => Icons.place_rounded,
                                    },
                                    subtitle: hit.matchedText == null
                                        ? null
                                        : (hit.reason == SearchMatchReason.alias
                                            ? 'Also known as "${hit.matchedText}"'
                                            : 'Near ${hit.matchedText}'),
                                    subtitleIcon: hit.reason == SearchMatchReason.landmark ? Icons.near_me_rounded : null,
                                    dimmed: hit.reason == SearchMatchReason.landmark,
                                    onTap: _pick,
                                  ),
                              ],
                            ),
            ),
          ],
        ),
      ),
    );
  }

  void _pick(Station station) {
    ref.read(localStoreProvider).recordSearchVisit(station.stopId);
    ref.invalidate(recentSearchIdsProvider);
    Navigator.of(context).pop(station);
  }
}

class _QuickPicks extends ConsumerWidget {
  const _QuickPicks({
    required this.favouriteIds,
    required this.recentIds,
    required this.byId,
    required this.isOrigin,
    required this.onPick,
  });

  final Set<String> favouriteIds;
  final List<String> recentIds;
  final Map<String, Station> byId;
  final bool isOrigin;
  final void Function(Station) onPick;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final favourites = [for (final id in favouriteIds) byId[id]].whereType<Station>().toList();
    final recents = [for (final id in recentIds) byId[id]]
        .whereType<Station>()
        .where((s) => !favouriteIds.contains(s.stopId))
        .take(8)
        .toList();

    final prediction = ref.watch(commutePredictionProvider).valueOrNull;
    Station? usual;
    if (prediction != null) {
      final usualStopId = isOrigin ? prediction.originStopId : prediction.destinationStopId;
      if (!favouriteIds.contains(usualStopId)) usual = byId[usualStopId];
    }

    if (usual == null && favourites.isEmpty && recents.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.xxl),
          child: EmptyState(icon: Icons.search_rounded, message: "Start typing and we'll find it.", compact: true),
        ),
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, AppSpacing.xxl),
      children: [
        if (usual != null) ...[
          const SearchSectionLabel('Your usual'),
          StationRow(station: usual, icon: Icons.insights_rounded, onTap: onPick),
        ],
        if (favourites.isNotEmpty) ...[
          const SearchSectionLabel('Favourites'),
          for (final station in favourites) StationRow(station: station, icon: Icons.star_rounded, onTap: onPick),
        ],
        if (recents.isNotEmpty) ...[
          const SearchSectionLabel('Recent'),
          for (final station in recents) StationRow(station: station, icon: Icons.history_rounded, onTap: onPick),
        ],
      ],
    );
  }
}
