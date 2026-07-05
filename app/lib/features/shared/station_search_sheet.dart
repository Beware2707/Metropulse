import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../domain/models/station.dart';
import '../../domain/search_index.dart';
import '../../providers/core_providers.dart';
import '../search/search_providers.dart';

/// A modal station picker shared by the Journey Planner and anywhere else
/// that needs one: offline search over stations + curated aliases +
/// curated exit landmarks, boosted by favourites/recents, with Recent /
/// Favourite / Nearby quick-pick chips when the query is empty.
class StationSearchSheet extends ConsumerStatefulWidget {
  const StationSearchSheet({super.key, this.title = 'Search stations'});

  final String title;

  @override
  ConsumerState<StationSearchSheet> createState() => _StationSearchSheetState();
}

class _StationSearchSheetState extends ConsumerState<StationSearchSheet> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final bundle = ref.watch(offlineBundleProvider).valueOrNull;
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
        height: MediaQuery.of(context).size.height * 0.8,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              child: TextField(
                autofocus: true,
                decoration: InputDecoration(
                  prefixIcon: const Icon(Icons.search),
                  hintText: widget.title,
                  border: const OutlineInputBorder(),
                ),
                onChanged: (value) => setState(() => _query = value),
              ),
            ),
            Expanded(
              child: trimmed.isEmpty
                  ? _QuickPicks(
                      favouriteIds: favouriteIds,
                      recentIds: recentIds,
                      byId: byId,
                      onPick: _pick,
                    )
                  : hits.isEmpty
                      ? const Center(child: Text('No stations match that search.'))
                      : ListView.builder(
                          itemCount: hits.length,
                          itemBuilder: (_, index) {
                            final hit = hits[index];
                            return ListTile(
                              leading: const Icon(Icons.place_outlined),
                              title: Text(hit.station.name),
                              subtitle: hit.matchedText == null
                                  ? null
                                  : Text(
                                      hit.reason == SearchMatchReason.alias
                                          ? 'Also known as "${hit.matchedText}"'
                                          : 'Near ${hit.matchedText}',
                                    ),
                              onTap: () => _pick(hit.station),
                            );
                          },
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

class _QuickPicks extends StatelessWidget {
  const _QuickPicks({
    required this.favouriteIds,
    required this.recentIds,
    required this.byId,
    required this.onPick,
  });

  final Set<String> favouriteIds;
  final List<String> recentIds;
  final Map<String, Station> byId;
  final void Function(Station) onPick;

  @override
  Widget build(BuildContext context) {
    final favourites = [for (final id in favouriteIds) byId[id]].whereType<Station>().toList();
    final recents = [for (final id in recentIds) byId[id]]
        .whereType<Station>()
        .where((s) => !favouriteIds.contains(s.stopId))
        .take(8)
        .toList();

    if (favourites.isEmpty && recents.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Start typing a station name, alias or nearby landmark.'),
        ),
      );
    }
    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 8),
      children: [
        if (favourites.isNotEmpty) ...[
          const _SectionLabel('Favourites'),
          for (final station in favourites)
            ListTile(
              leading: const Icon(Icons.star, size: 20),
              title: Text(station.name),
              onTap: () => onPick(station),
            ),
        ],
        if (recents.isNotEmpty) ...[
          const _SectionLabel('Recent'),
          for (final station in recents)
            ListTile(
              leading: const Icon(Icons.history, size: 20),
              title: Text(station.name),
              onTap: () => onPick(station),
            ),
        ],
      ],
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Text(
        text.toUpperCase(),
        style: Theme.of(context)
            .textTheme
            .labelSmall
            ?.copyWith(color: Theme.of(context).colorScheme.outline, letterSpacing: 1),
      ),
    );
  }
}
