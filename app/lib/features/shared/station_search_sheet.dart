import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/icon_badge.dart';
import '../../domain/models/station.dart';
import '../../domain/search_index.dart';
import '../../providers/core_providers.dart';
import '../search/search_providers.dart';

/// A modal station picker shared by the Journey Planner and anywhere else
/// that needs one: offline search over stations + curated aliases +
/// curated exit landmarks, boosted by favourites/recents, with Recent /
/// Favourite quick-pick rows when the query is empty.
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
        height: MediaQuery.of(context).size.height * 0.85,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, AppSpacing.sm),
              child: TextField(
                autofocus: true,
                decoration: InputDecoration(prefixIcon: const Icon(Icons.search_rounded), hintText: widget.title),
                onChanged: (value) => setState(() => _query = value),
              ),
            ),
            Expanded(
              child: trimmed.isEmpty
                  ? _QuickPicks(favouriteIds: favouriteIds, recentIds: recentIds, byId: byId, onPick: _pick)
                  : hits.isEmpty
                      ? const Center(child: Text('No stations match that search.'))
                      : ListView.separated(
                          padding: const EdgeInsets.fromLTRB(AppSpacing.lg, 0, AppSpacing.lg, AppSpacing.xxl),
                          itemCount: hits.length,
                          separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
                          itemBuilder: (_, index) {
                            final hit = hits[index];
                            return GlassSurface(
                              onTap: () => _pick(hit.station),
                              child: Row(
                                children: [
                                  const IconBadge(icon: Icons.place_rounded),
                                  const SizedBox(width: AppSpacing.md),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(hit.station.name, style: Theme.of(context).textTheme.titleMedium),
                                        if (hit.matchedText != null)
                                          Text(
                                            hit.reason == SearchMatchReason.alias
                                                ? 'Also known as "${hit.matchedText}"'
                                                : 'Near ${hit.matchedText}',
                                            style: Theme.of(context).textTheme.bodySmall,
                                          ),
                                      ],
                                    ),
                                  ),
                                ],
                              ),
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
          padding: EdgeInsets.all(AppSpacing.xxl),
          child: Text('Start typing a station name, alias or nearby landmark.'),
        ),
      );
    }
    return ListView(
      padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, AppSpacing.xxl),
      children: [
        if (favourites.isNotEmpty) ...[
          const _SectionLabel('Favourites'),
          for (final station in favourites) _Row(station: station, icon: Icons.star_rounded, onTap: onPick),
        ],
        if (recents.isNotEmpty) ...[
          const _SectionLabel('Recent'),
          for (final station in recents) _Row(station: station, icon: Icons.history_rounded, onTap: onPick),
        ],
      ],
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.station, required this.icon, required this.onTap});

  final Station station;
  final IconData icon;
  final void Function(Station) onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: GlassSurface(
        onTap: () => onTap(station),
        child: Row(
          children: [
            IconBadge(icon: icon, color: AppColors.brandBlue.withValues(alpha: 0.14), foreground: AppColors.brandBlue),
            const SizedBox(width: AppSpacing.md),
            Expanded(child: Text(station.name, style: Theme.of(context).textTheme.titleMedium)),
          ],
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, AppSpacing.md, 4, AppSpacing.sm),
      child: Text(text.toUpperCase(), style: Theme.of(context).textTheme.labelSmall),
    );
  }
}
