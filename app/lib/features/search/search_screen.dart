import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_motion.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/search_entry_pill.dart';
import '../../core/widgets/station_row.dart';
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
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

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
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, AppSpacing.sm),
                child: Row(
                  children: [
                    IconPillButton(icon: Icons.arrow_back_rounded, onPressed: () => context.pop()),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: Hero(
                        tag: kSearchHeroTag,
                        child: Material(
                          type: MaterialType.transparency,
                          child: GlassSurface(
                            borderRadius: AppRadius.pillR,
                            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl, vertical: 2),
                            child: Row(
                              children: [
                                Icon(Icons.search_rounded, size: 24, color: Theme.of(context).colorScheme.onSurfaceVariant),
                                const SizedBox(width: AppSpacing.md),
                                Expanded(
                                  child: TextField(
                                    controller: _controller,
                                    autofocus: true,
                                    style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
                                    decoration: const InputDecoration(
                                      hintText: 'Where to?',
                                      border: InputBorder.none,
                                      isDense: true,
                                      contentPadding: EdgeInsets.symmetric(vertical: 16),
                                    ),
                                    onChanged: (value) => setState(() => _query = value),
                                  ),
                                ),
                                if (_query.isNotEmpty)
                                  GestureDetector(
                                    onTap: () {
                                      _controller.clear();
                                      setState(() => _query = '');
                                    },
                                    child: Icon(Icons.close_rounded,
                                        size: 20, color: Theme.of(context).colorScheme.onSurfaceVariant),
                                  ),
                              ],
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: AnimatedSwitcher(
                  duration: AppMotion.medium,
                  child: _buildBody(
                    bundle: bundle,
                    stations: stations,
                    trimmed: trimmed,
                    hits: hits,
                    favouriteIds: favouriteIds,
                    recentIds: recentIds,
                    byId: byId,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _openStation(Station station) {
    ref.read(localStoreProvider).recordSearchVisit(station.stopId);
    ref.invalidate(recentSearchIdsProvider);
    context.push('/station/${station.stopId}');
  }

  Widget _buildBody({
    required AsyncValue<OfflineBundle?> bundle,
    required List<Station> stations,
    required String trimmed,
    required List<SearchHit> hits,
    required Set<String> favouriteIds,
    required List<String> recentIds,
    required Map<String, Station> byId,
  }) {
    if (bundle.isLoading) {
      return const KeyedSubtree(
        key: ValueKey('loading'),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (stations.isEmpty) {
      return const KeyedSubtree(
        key: ValueKey('no-offline-data'),
        child: Center(
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.xxl),
            child: EmptyState(
              icon: Icons.cloud_off_rounded,
              message: "We haven't downloaded station data yet — connect once and we'll take care of it.",
            ),
          ),
        ),
      );
    }
    if (trimmed.isEmpty) {
      return KeyedSubtree(
        key: const ValueKey('recents-and-favourites'),
        child: _RecentAndFavourites(
          favouriteIds: favouriteIds,
          recentIds: recentIds,
          byId: byId,
          onTap: _openStation,
        ),
      );
    }
    if (hits.isEmpty) {
      return const KeyedSubtree(
        key: ValueKey('no-results'),
        child: Center(
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.xxl),
            child: EmptyState(
              icon: Icons.search_off_rounded,
              message: "We couldn't find that one — try a different name or landmark.",
            ),
          ),
        ),
      );
    }
    return KeyedSubtree(
      key: const ValueKey('results'),
      child: _ResultsList(hits: hits, onTap: _openStation),
    );
  }
}

class _ResultsList extends StatelessWidget {
  const _ResultsList({required this.hits, required this.onTap});

  final List<SearchHit> hits;
  final void Function(Station) onTap;

  @override
  Widget build(BuildContext context) {
    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, AppSpacing.xxl),
      itemCount: hits.length,
      separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
      itemBuilder: (_, index) {
        final hit = hits[index];
        return StationRow(
          station: hit.station,
          icon: switch (hit.reason) {
            SearchMatchReason.alias => Icons.label_outline_rounded,
            SearchMatchReason.landmark => Icons.near_me_rounded,
            SearchMatchReason.name => Icons.place_rounded,
          },
          subtitle: hit.matchedText == null
              ? null
              : (hit.reason == SearchMatchReason.alias ? 'Also known as "${hit.matchedText}"' : 'Near ${hit.matchedText}'),
          subtitleIcon: hit.reason == SearchMatchReason.landmark ? Icons.near_me_rounded : null,
          dimmed: hit.reason == SearchMatchReason.landmark,
          onTap: onTap,
        );
      },
    );
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
          padding: EdgeInsets.all(AppSpacing.xxl),
          child: EmptyState(icon: Icons.search_rounded, message: "Start typing and we'll find it."),
        ),
      );
    }

    // Top pick: the single most relevant station right now — the last
    // place you searched for if there is one, else your first favourite —
    // pulled out and given its own visual weight so a daily commuter's most
    // likely destination isn't buried in an equally-weighted list.
    final topPickIsRecent = recents.isNotEmpty;
    final topPick = topPickIsRecent ? recents.first : (favourites.isNotEmpty ? favourites.first : null);
    final remainingFavourites = topPickIsRecent ? favourites : favourites.skip(1).toList();
    final remainingRecents = topPickIsRecent ? recents.skip(1).toList() : recents;

    return ListView(
      padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, AppSpacing.xxl),
      children: [
        if (topPick != null) ...[
          _TopPickCard(station: topPick, isRecent: topPickIsRecent, onTap: onTap),
          const SizedBox(height: AppSpacing.lg),
        ],
        if (remainingFavourites.isNotEmpty) ...[
          const SearchSectionLabel('Favourites', topSpacing: AppSpacing.lg),
          for (final station in remainingFavourites) StationRow(station: station, icon: Icons.star_rounded, onTap: onTap),
        ],
        if (remainingRecents.isNotEmpty) ...[
          const SearchSectionLabel('Recent searches', topSpacing: AppSpacing.lg),
          for (final station in remainingRecents) StationRow(station: station, icon: Icons.history_rounded, onTap: onTap),
        ],
      ],
    );
  }
}

class _TopPickCard extends StatelessWidget {
  const _TopPickCard({required this.station, required this.isRecent, required this.onTap});

  final Station station;
  final bool isRecent;
  final void Function(Station) onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return GlassSurface(
      onTap: () => onTap(station),
      child: Row(
        children: [
          IconBadge(
            icon: isRecent ? Icons.history_rounded : Icons.star_rounded,
            gradient: AppColors.heroGradientFor(),
          ),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(isRecent ? 'BACK TO' : 'FAVOURITE', style: theme.textTheme.labelSmall),
                Text(station.name, style: theme.textTheme.titleLarge),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded),
        ],
      ),
    );
  }
}

