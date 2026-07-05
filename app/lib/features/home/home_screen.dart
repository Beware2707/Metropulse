import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters.dart';
import '../../core/l10n_ext.dart';
import '../../domain/fare.dart';
import '../../domain/models/commute_card.dart';
import '../../domain/models/journey.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import '../shared/async_section.dart';
import '../shared/widgets.dart';
import 'home_providers.dart';

export 'home_providers.dart' show activeJourneyProvider, commuteCardProvider;

/// Home: the commuter dashboard. The commute card answers "when do I leave,
/// what do I board, which platform/coach, am I delayed" before anything else;
/// map and planner are one tap away but never the first thing.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(
        title: Text(context.t.appTitle),
        actions: [
          const Padding(
            padding: EdgeInsets.only(right: 8),
            child: Center(child: LiveIndicator()),
          ),
          IconButton(
            tooltip: 'Live map',
            icon: const Icon(Icons.map_outlined),
            onPressed: () => context.push('/map'),
          ),
          IconButton(
            tooltip: 'Settings',
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => context.push('/settings'),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/planner'),
        icon: const Icon(Icons.route_outlined),
        label: Text(context.t.journeyPlanCta),
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          ref
            ..invalidate(commuteCardProvider)
            ..invalidate(activeJourneyProvider)
            ..invalidate(activeAlertsProvider)
            ..invalidate(recentJourneysProvider)
            ..invalidate(favouriteStationsProvider)
            ..invalidate(homeLastTrainProvider)
            ..invalidate(nearbyStationsProvider);
        },
        child: LayoutBuilder(
          builder: (context, constraints) {
            final isWide = constraints.maxWidth >= 720;
            final content = _HomeContent(isWide: isWide);
            // Tablets: cap line length and centre the dashboard.
            return Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 1100),
                child: content,
              ),
            );
          },
        ),
      ),
    );
  }
}

class _HomeContent extends ConsumerWidget {
  const _HomeContent({required this.isWide});

  final bool isWide;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final journey = ref.watch(activeJourneyProvider).valueOrNull;

    final primary = <Widget>[
      const _QuickSearchBar(),
      if (journey != null) const _ActiveJourneyBanner(),
      const _CommuteSection(),
      const _AlertsSection(),
    ];
    final secondary = <Widget>[
      const _FavouritesSection(),
      const _NearbySection(),
      const _LastTrainSection(),
      const _RecentJourneysSection(),
    ];

    if (!isWide) {
      return ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
        children: [...primary, ...secondary],
      );
    }
    // Two-column tablet layout: the commute story left, browsing right.
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 3, child: Column(children: primary)),
          const SizedBox(width: 16),
          Expanded(flex: 2, child: Column(children: secondary)),
        ],
      ),
    );
  }
}

// --- Quick search ------------------------------------------------------------

class _QuickSearchBar extends StatelessWidget {
  const _QuickSearchBar();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(28),
        child: InkWell(
          borderRadius: BorderRadius.circular(28),
          onTap: () => context.push('/search'),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Row(
              children: [
                Icon(Icons.search, color: scheme.onSurfaceVariant),
                const SizedBox(width: 12),
                Text('Search stations, aliases, landmarks…',
                    style: TextStyle(color: scheme.onSurfaceVariant)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// --- Commute card -------------------------------------------------------------

class _CommuteSection extends ConsumerWidget {
  const _CommuteSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final card = ref.watch(commuteCardProvider);
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: card.when(
        loading: () => const SkeletonBlock(height: 220),
        error: (_, __) => Card(
          child: ListTile(
            leading: const Icon(Icons.cloud_off),
            title: Text(context.t.homeSectionError),
            trailing: TextButton(
              onPressed: () => ref.invalidate(commuteCardProvider),
              child: Text(context.t.retry),
            ),
          ),
        ),
        data: (data) => data == null
            ? const _SetupCommuteCard()
            : _CommuteCardView(card: data),
      ),
    );
  }
}

class _CommuteCardView extends ConsumerWidget {
  const _CommuteCardView({required this.card});

  final CommuteCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final suggestedPlan = ref.watch(homeSuggestedPlanProvider).valueOrNull;
    final fare = suggestedPlan == null ? null : estimateFare(suggestedPlan);
    return Semantics(
      label: 'Commute card: ${card.originName} to ${card.destinationName}',
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(card.greeting, style: theme.textTheme.titleMedium),
              const SizedBox(height: 4),
              Text(
                '${card.originName} → ${card.destinationName}',
                style: theme.textTheme.headlineSmall
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 8),
              if (card.routeLongName != null)
                LineBadge(label: card.routeLongName!, colorHex: card.routeColor),
              const SizedBox(height: 16),
              if (card.leaveInSeconds != null)
                Text(
                  context.t.homeLeaveIn(minutesLabel(card.leaveInSeconds)),
                  style: theme.textTheme.titleLarge?.copyWith(
                    color: theme.colorScheme.primary,
                    fontWeight: FontWeight.w800,
                  ),
                )
              else
                Text(context.t.homeNoDepartures,
                    style: theme.textTheme.titleMedium),
              const SizedBox(height: 16),
              Wrap(
                spacing: 24,
                runSpacing: 12,
                children: [
                  StatTile(
                      label: context.t.nextMetro,
                      value: clockTime(card.nextDepartureAt)),
                  StatTile(label: context.t.crowding, value: card.crowding),
                  if (card.platformHint != null)
                    StatTile(
                        label: context.t.platform, value: card.platformHint!),
                  if (card.recommendedCoach != null)
                    StatTile(
                        label: context.t.journeyCoach,
                        value: '${card.recommendedCoach! + 1}'),
                  StatTile(
                      label: context.t.eta,
                      value: minutesLabel(card.travelSeconds)),
                  if (fare != null)
                    StatTile(label: 'Fare (est.)', value: '₹${fare.rupees}'),
                  if (card.interchangeNames.isNotEmpty)
                    StatTile(
                        label: context.t.interchange,
                        value: card.interchangeNames.join(', ')),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SetupCommuteCard extends StatelessWidget {
  const _SetupCommuteCard();

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.all(16),
        leading: const Icon(Icons.add_home_work_outlined, size: 36),
        title: Text(context.t.homeSetupCommuteTitle),
        subtitle: Text(context.t.homeSetupCommuteBody),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => context.push('/favourites'),
      ),
    );
  }
}

class _ActiveJourneyBanner extends StatelessWidget {
  const _ActiveJourneyBanner();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: scheme.primaryContainer,
      child: ListTile(
        leading: Icon(Icons.navigation, color: scheme.onPrimaryContainer),
        title: Text(context.t.journeyInProgress),
        subtitle: Text(context.t.journeyReturnTap),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => context.push('/journey'),
      ),
    );
  }
}

// --- Alerts ---------------------------------------------------------------------

class _AlertsSection extends ConsumerWidget {
  const _AlertsSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // REST snapshot on load; live WS alert frames refresh it for free.
    ref.listen(serviceAlertBannerProvider, (_, __) {
      ref.invalidate(activeAlertsProvider);
    });
    final alerts = ref.watch(activeAlertsProvider);
    return AsyncSection<List<Map<String, dynamic>>>(
      title: context.t.homeLiveAlerts,
      value: alerts,
      isEmpty: (data) => data.isEmpty,
      emptyMessage: context.t.homeNoAlerts,
      onRetry: () => ref.invalidate(activeAlertsProvider),
      builder: (context, data) => Column(
        children: [
          for (final alert in data)
            Card(
              child: ListTile(
                leading: Icon(
                  switch ('${alert['severity']}') {
                    'severe' => Icons.error_outline,
                    'warning' => Icons.warning_amber_outlined,
                    _ => Icons.info_outline,
                  },
                  color: switch ('${alert['severity']}') {
                    'severe' => Theme.of(context).colorScheme.error,
                    'warning' => Colors.orange,
                    _ => null,
                  },
                ),
                title: Text('${alert['title']}'),
                subtitle: Text('${alert['description']}',
                    maxLines: 2, overflow: TextOverflow.ellipsis),
              ),
            ),
        ],
      ),
    );
  }
}

// --- Favourites -----------------------------------------------------------------

class _FavouritesSection extends ConsumerWidget {
  const _FavouritesSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final favourites = ref.watch(favouriteStationsProvider);
    final stations = ref.watch(stationIndexProvider);
    return AsyncSection<List<Map<String, dynamic>>>(
      title: context.t.homeFavouriteStations,
      value: favourites,
      isEmpty: (data) => data.isEmpty,
      emptyMessage: context.t.homeNoFavourites,
      onRetry: () => ref.invalidate(favouriteStationsProvider),
      trailing: IconButton(
        tooltip: 'Manage favourites',
        icon: const Icon(Icons.edit_outlined, size: 18),
        onPressed: () => context.push('/favourites'),
      ),
      builder: (context, data) => Wrap(
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final row in data)
            ActionChip(
              avatar: Icon(switch ('${row['label']}'.toLowerCase()) {
                'home' => Icons.home_outlined,
                'work' => Icons.work_outline,
                _ => Icons.star_outline,
              }, size: 18),
              label: Text(
                  stations['${row['stop_id']}']?.name ?? '${row['stop_id']}'),
              onPressed: () => context.push('/station/${row['stop_id']}'),
            ),
        ],
      ),
    );
  }
}

// --- Nearby ---------------------------------------------------------------------

class _NearbySection extends ConsumerWidget {
  const _NearbySection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final nearby = ref.watch(nearbyStationsProvider);
    return AsyncSection<NearbyState>(
      title: context.t.homeNearbyStations,
      value: nearby,
      isEmpty: (state) => state is NearbyUnavailable,
      emptyMessage: context.t.homeLocationOff,
      onRetry: () => ref.invalidate(nearbyStationsProvider),
      builder: (context, state) => switch (state) {
        NearbyNeedsPermission() => Card(
            child: ListTile(
              leading: const Icon(Icons.location_off_outlined),
              title: Text(context.t.homeLocationOff),
              trailing: TextButton(
                onPressed: () => ref.invalidate(nearbyStationsProvider),
                child: Text(context.t.homeEnableLocation),
              ),
            ),
          ),
        NearbyReady(:final stations) => Column(
            children: [
              for (final nearbyStation in stations)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.place_outlined),
                    title: Text(nearbyStation.station.name),
                    subtitle:
                        Text(distanceLabel(nearbyStation.distanceM)),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => context
                        .push('/station/${nearbyStation.station.stopId}'),
                  ),
                ),
            ],
          ),
        NearbyUnavailable() => const SizedBox.shrink(),
      },
    );
  }
}

// --- Last train -----------------------------------------------------------------

class _LastTrainSection extends ConsumerWidget {
  const _LastTrainSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lastTrain = ref.watch(homeLastTrainProvider);
    final stations = ref.watch(stationIndexProvider);
    return AsyncSection<Map<String, dynamic>?>(
      title: context.t.homeLastTrain,
      value: lastTrain,
      isEmpty: (data) => data == null,
      emptyMessage: context.t.homeNoLastTrain,
      onRetry: () => ref.invalidate(homeLastTrainProvider),
      builder: (context, data) {
        final info = data!;
        final departure = DateTime.tryParse('${info['departure_at']}');
        final stationName =
            stations['${info['stop_id']}']?.name ?? '${info['stop_id']}';
        return Card(
          child: ListTile(
            leading: const Icon(Icons.nightlight_outlined),
            title: Text('$stationName · ${clockTime(departure)}'),
            subtitle: Text('${info['headsign'] ?? info['route_id']}'),
            trailing: TextButton(
              onPressed: () async {
                final messenger = ScaffoldMessenger.of(context);
                await ref.read(remindersRepositoryProvider).createLastTrain(
                      stopId: '${info['stop_id']}',
                      routeId: info['route_id'] as String?,
                    );
                messenger.showSnackBar(
                  const SnackBar(content: Text("You'll be reminded before it departs.")),
                );
              },
              child: const Text('Remind me'),
            ),
            onTap: () => context.push('/station/${info['stop_id']}'),
          ),
        );
      },
    );
  }
}

// --- Recent journeys --------------------------------------------------------------

class _RecentJourneysSection extends ConsumerWidget {
  const _RecentJourneysSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final journeys = ref.watch(recentJourneysProvider);
    final stations = ref.watch(stationIndexProvider);
    return AsyncSection<List<Journey>>(
      title: context.t.homeRecentJourneys,
      value: journeys,
      isEmpty: (data) => data.isEmpty,
      emptyMessage: context.t.homeNoRecentJourneys,
      onRetry: () => ref.invalidate(recentJourneysProvider),
      trailing: TextButton(
        onPressed: () => context.push('/journeys/history'),
        child: const Text('See all'),
      ),
      builder: (context, data) => Column(
        children: [
          for (final journey in data)
            Card(
              child: ListTile(
                leading: Icon(switch (journey.status) {
                  'completed' => Icons.check_circle_outline,
                  'missed' => Icons.error_outline,
                  _ => Icons.remove_circle_outline,
                }),
                title: Text(
                  '${stations[journey.originStopId]?.name ?? journey.originStopId}'
                  ' → '
                  '${stations[journey.destinationStopId]?.name ?? journey.destinationStopId}',
                ),
                subtitle: Text(journey.status),
                onTap: () => context.push('/planner'),
              ),
            ),
        ],
      ),
    );
  }
}
