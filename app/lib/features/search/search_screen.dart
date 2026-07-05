import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../domain/models/station.dart';
import '../../domain/search_index.dart';
import '../../providers/core_providers.dart';
import 'search_providers.dart';

/// Full-page station search: fully offline (stations, curated aliases, and
/// curated exit landmarks all come from the cached offline bundle), ranked
/// and boosted by favourites/recents. No network call happens while typing.
class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final bundle = ref.watch(offlineBundleProvider);
    final stations = bundle.valueOrNull?.stations ?? const <Station>[];
    final exits = bundle.valueOrNull?.exits ?? const <String, List<StationExitInfo>>{};
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

    return Scaffold(
      appBar: AppBar(title: const Text('Search stations')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              autofocus: true,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Station, alias or nearby landmark',
                border: OutlineInputBorder(),
              ),
              onChanged: (value) => setState(() => _query = value),
            ),
          ),
          if (bundle.isLoading)
            const Expanded(child: Center(child: CircularProgressIndicator()))
          else if (stations.isEmpty)
            const Expanded(
              child: Center(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(
                    'Station data not downloaded yet.\n'
                    'Connect once to cache the network for offline use.',
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            )
          else if (trimmed.isEmpty)
            Expanded(
              child: _RecentAndFavourites(
                favouriteIds: favouriteIds,
                recentIds: recentIds,
                byId: byId,
                onTap: _openStation,
              ),
            )
          else if (hits.isEmpty)
            const Expanded(
              child: Center(child: Text('No stations match that search.')),
            )
          else
            Expanded(
              child: ListView.builder(
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
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => _openStation(hit.station),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }

  void _openStation(Station station) {
    ref.read(localStoreProvider).recordSearchVisit(station.stopId);
    ref.invalidate(recentSearchIdsProvider);
    context.push('/station/${station.stopId}');
  }
}

class _RecentAndFavourites extends StatelessWidget {
  const _RecentAndFavourites({
    required this.favouriteIds,
    required this.recentIds,
    required this.byId,
    required this.onTap,
  });

  final Set<String> favouriteIds;
  final List<String> recentIds;
  final Map<String, Station> byId;
  final void Function(Station) onTap;

  @override
  Widget build(BuildContext context) {
    final favourites = [for (final id in favouriteIds) byId[id]].whereType<Station>().toList();
    final recents = [for (final id in recentIds) byId[id]]
        .whereType<Station>()
        .where((s) => !favouriteIds.contains(s.stopId))
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
      children: [
        if (favourites.isNotEmpty) ...[
          const _SectionHeader('Favourites'),
          for (final station in favourites)
            ListTile(
              leading: const Icon(Icons.star),
              title: Text(station.name),
              onTap: () => onTap(station),
            ),
        ],
        if (recents.isNotEmpty) ...[
          const _SectionHeader('Recent searches'),
          for (final station in recents)
            ListTile(
              leading: const Icon(Icons.history),
              title: Text(station.name),
              onTap: () => onTap(station),
            ),
        ],
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
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
