import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/l10n_ext.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/async_section.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/live_indicator.dart';
import '../../core/widgets/reveal_animations.dart';
import '../../core/widgets/search_entry_pill.dart';
import '../../core/widgets/shimmer_skeleton.dart';
import '../../domain/fare.dart';
import '../../domain/models/commute_card.dart';
import '../../domain/models/journey.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import 'home_providers.dart';

export 'home_providers.dart' show activeJourneyProvider, commuteCardProvider;

String _greeting() {
  final hour = DateTime.now().hour;
  if (hour < 5) return 'Still up?';
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  if (hour < 21) return 'Good evening';
  return 'Good night';
}

/// Home: the commuter dashboard. The commute card answers "when do I leave,
/// what do I board, which platform/coach, am I delayed" before anything
/// else; map and planner are one tap away but never the first thing.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      body: AmbientBackground(
        child: SafeArea(
          bottom: false,
          child: Stack(
            children: [
              RefreshIndicator(
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
                    return Center(
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(maxWidth: 1100),
                        child: _HomeContent(isWide: isWide),
                      ),
                    );
                  },
                ),
              ),
              Positioned(
                right: AppSpacing.lg,
                bottom: 108,
                child: PrimaryButton(
                  label: context.t.journeyPlanCta,
                  icon: Icons.alt_route_rounded,
                  onPressed: () => context.push('/planner'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_greeting(), style: theme.textTheme.bodyLarge),
              Text('MetroPulse', style: theme.textTheme.displaySmall),
            ],
          ),
        ),
        const LiveIndicator(),
        const SizedBox(width: AppSpacing.sm),
        IconPillButton(
          icon: Icons.notifications_none_rounded,
          tooltip: 'Notifications',
          onPressed: () => context.push('/notifications'),
        ),
      ],
    );
  }
}

class _HomeContent extends ConsumerWidget {
  const _HomeContent({required this.isWide});

  final bool isWide;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final journey = ref.watch(activeJourneyProvider).valueOrNull;

    final primaryRaw = <Widget>[
      const _Header(),
      const SizedBox(height: AppSpacing.xl),
      SearchEntryPill(hint: 'Where to?', onTap: () => context.push('/search')),
      if (journey != null) const _ActiveJourneyBanner(),
      const _CommuteHero(),
      const _AlertsSection(),
    ];
    final secondaryRaw = <Widget>[
      const _FavouritesSection(),
      const _NearbySection(),
      const _LastTrainSection(),
      const _RecentJourneysSection(),
    ];
    final primary = [
      for (var i = 0; i < primaryRaw.length; i++)
        DelayedReveal(delay: Duration(milliseconds: 40 * i), child: primaryRaw[i]),
    ];
    final secondary = [
      for (var i = 0; i < secondaryRaw.length; i++)
        DelayedReveal(delay: Duration(milliseconds: 60 * i + 120), child: secondaryRaw[i]),
    ];

    if (!isWide) {
      return ListView(
        padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, 180),
        children: [...primary, ...secondary],
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, 180),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(flex: 3, child: Column(children: primary)),
          const SizedBox(width: AppSpacing.lg),
          Expanded(flex: 2, child: Column(children: secondary)),
        ],
      ),
    );
  }
}

// --- Commute hero --------------------------------------------------------------

class _CommuteHero extends ConsumerWidget {
  const _CommuteHero();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final card = ref.watch(commuteCardProvider);
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.xl),
      child: card.when(
        loading: () => const ShimmerBlock(height: 240, radius: AppRadius.xl),
        error: (_, __) => EmptyState(
          icon: Icons.cloud_off_rounded,
          message: context.t.homeSectionError,
          actionLabel: context.t.retry,
          onAction: () => ref.invalidate(commuteCardProvider),
        ),
        data: (data) => data == null ? const _SetupCommuteCard() : _CommuteCardView(card: data),
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
      child: GlassSurface(
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: AppColors.heroGradientWide,
        ),
        border: false,
        padding: const EdgeInsets.all(AppSpacing.xxl),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(card.greeting, style: theme.textTheme.titleMedium?.copyWith(color: Colors.white70)),
            const SizedBox(height: 4),
            Text(
              '${card.originName} → ${card.destinationName}',
              style: theme.textTheme.headlineSmall?.copyWith(color: Colors.white),
            ),
            const SizedBox(height: 14),
            if (card.routeLongName != null) LineChip(label: card.routeLongName!, colorHex: card.routeColor),
            const SizedBox(height: 22),
            if (card.leaveInSeconds != null)
              Text(
                context.t.homeLeaveIn(minutesLabel(card.leaveInSeconds)),
                style: theme.textTheme.displaySmall?.copyWith(color: Colors.white),
              )
            else
              Text(context.t.homeNoDepartures, style: theme.textTheme.titleMedium?.copyWith(color: Colors.white)),
            const SizedBox(height: 22),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                _HeroStat(label: context.t.nextMetro, value: clockTime(card.nextDepartureAt)),
                _HeroStat(label: context.t.crowding, value: card.crowding),
                if (card.platformHint != null) _HeroStat(label: context.t.platform, value: card.platformHint!),
                if (card.recommendedCoach != null)
                  _HeroStat(label: context.t.journeyCoach, value: '${card.recommendedCoach! + 1}'),
                _HeroStat(label: context.t.eta, value: minutesLabel(card.travelSeconds)),
                if (fare != null) _HeroStat(label: 'Fare (est.)', value: '₹${fare.rupees}'),
                if (card.interchangeNames.isNotEmpty)
                  _HeroStat(label: context.t.interchange, value: card.interchangeNames.join(', ')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _HeroStat extends StatelessWidget {
  const _HeroStat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.16), borderRadius: AppRadius.mdR),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 180),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(label.toUpperCase(),
                style: const TextStyle(
                    color: Colors.white70, fontSize: 10, fontWeight: FontWeight.w800, letterSpacing: 0.6)),
            Text(value,
                style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.w800),
                maxLines: 2,
                overflow: TextOverflow.ellipsis),
          ],
        ),
      ),
    );
  }
}

class _SetupCommuteCard extends StatelessWidget {
  const _SetupCommuteCard();

  @override
  Widget build(BuildContext context) {
    return GlassSurface(
      onTap: () => context.push('/favourites'),
      child: Row(
        children: [
          IconBadge(icon: Icons.add_home_work_rounded, gradient: AppColors.heroGradientFor(), size: 52, iconSize: 26),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(context.t.homeSetupCommuteTitle, style: Theme.of(context).textTheme.titleLarge),
                const SizedBox(height: 4),
                Text(context.t.homeSetupCommuteBody, style: Theme.of(context).textTheme.bodyMedium),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded),
        ],
      ),
    );
  }
}

class _ActiveJourneyBanner extends StatelessWidget {
  const _ActiveJourneyBanner();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.lg),
      child: GlassSurface(
        gradient: LinearGradient(colors: [AppColors.live.withValues(alpha: 0.92), AppColors.brandBlue.withValues(alpha: 0.92)]),
        border: false,
        onTap: () => context.push('/journey'),
        child: Row(
          children: [
            const Icon(Icons.navigation_rounded, color: Colors.white),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(context.t.journeyInProgress,
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 16)),
                  Text(context.t.journeyReturnTap, style: const TextStyle(color: Colors.white70, fontSize: 13)),
                ],
              ),
            ),
            const Icon(Icons.chevron_right_rounded, color: Colors.white),
          ],
        ),
      ),
    );
  }
}

// --- Alerts ---------------------------------------------------------------------

class _AlertsSection extends ConsumerWidget {
  const _AlertsSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(serviceAlertBannerProvider, (_, __) => ref.invalidate(activeAlertsProvider));
    final alerts = ref.watch(activeAlertsProvider);
    return AsyncSection<List<Map<String, dynamic>>>(
      title: context.t.homeLiveAlerts,
      value: alerts,
      isEmpty: (data) => data.isEmpty,
      emptyMessage: context.t.homeNoAlerts,
      emptyIcon: Icons.verified_rounded,
      onRetry: () => ref.invalidate(activeAlertsProvider),
      builder: (context, data) => Column(
        children: [
          for (final alert in data)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: GlassSurface(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    IconBadge(
                      icon: switch ('${alert['severity']}') {
                        'severe' => Icons.error_rounded,
                        'warning' => Icons.warning_rounded,
                        _ => Icons.info_rounded,
                      },
                      color: switch ('${alert['severity']}') {
                        'severe' => AppColors.danger.withValues(alpha: 0.16),
                        'warning' => AppColors.warning.withValues(alpha: 0.16),
                        _ => null,
                      },
                      foreground: switch ('${alert['severity']}') {
                        'severe' => AppColors.danger,
                        'warning' => AppColors.warning,
                        _ => null,
                      },
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('${alert['title']}', style: Theme.of(context).textTheme.titleMedium),
                          Text('${alert['description']}',
                              maxLines: 2, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodyMedium),
                        ],
                      ),
                    ),
                  ],
                ),
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
      emptyIcon: Icons.star_rounded,
      onRetry: () => ref.invalidate(favouriteStationsProvider),
      trailing: IconPillButton(
        icon: Icons.edit_rounded,
        tooltip: 'Manage favourites',
        onPressed: () => context.push('/favourites'),
      ),
      builder: (context, data) => SizedBox(
        height: 96,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: data.length,
          separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.md),
          itemBuilder: (context, index) {
            final row = data[index];
            final name = stations['${row['stop_id']}']?.name ?? '${row['stop_id']}';
            final label = '${row['label'] ?? ''}'.toLowerCase();
            final icon = switch (label) {
              'home' => Icons.home_rounded,
              'work' => Icons.work_rounded,
              _ => Icons.star_rounded,
            };
            return _FavouriteChip(name: name, icon: icon, onTap: () => context.push('/station/${row['stop_id']}'));
          },
        ),
      ),
    );
  }
}

class _FavouriteChip extends StatelessWidget {
  const _FavouriteChip({required this.name, required this.icon, required this.onTap});

  final String name;
  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: 76,
        child: Column(
          children: [
            Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(gradient: AppColors.heroGradientFor(), shape: BoxShape.circle),
              child: Icon(icon, color: Colors.white, size: 24),
            ),
            const SizedBox(height: 6),
            Text(name,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.labelMedium?.copyWith(color: Theme.of(context).colorScheme.onSurface)),
          ],
        ),
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
      emptyIcon: Icons.location_off_rounded,
      onRetry: () => ref.invalidate(nearbyStationsProvider),
      builder: (context, state) => switch (state) {
        NearbyNeedsPermission() => GlassSurface(
            child: Row(
              children: [
                const IconBadge(icon: Icons.location_off_rounded),
                const SizedBox(width: AppSpacing.md),
                Expanded(child: Text(context.t.homeLocationOff, style: Theme.of(context).textTheme.bodyMedium)),
                GhostButton(
                    label: context.t.homeEnableLocation, onPressed: () => ref.invalidate(nearbyStationsProvider)),
              ],
            ),
          ),
        NearbyReady(:final stations) => SizedBox(
            height: 116,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: stations.length,
              separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.md),
              itemBuilder: (context, index) {
                final nearbyStation = stations[index];
                return _NearbyCard(
                  name: nearbyStation.station.name,
                  distance: distanceLabel(nearbyStation.distanceM),
                  onTap: () => context.push('/station/${nearbyStation.station.stopId}'),
                );
              },
            ),
          ),
        NearbyUnavailable() => const SizedBox.shrink(),
      },
    );
  }
}

class _NearbyCard extends StatelessWidget {
  const _NearbyCard({required this.name, required this.distance, required this.onTap});

  final String name;
  final String distance;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 152,
      child: GlassSurface(
        onTap: onTap,
        padding: const EdgeInsets.all(AppSpacing.md),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const IconBadge(icon: Icons.place_rounded, size: 36, iconSize: 18),
            const SizedBox(height: AppSpacing.sm),
            Text(name, maxLines: 1, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.titleSmall),
            Text(distance, style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      ),
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
      emptyIcon: Icons.nightlight_rounded,
      onRetry: () => ref.invalidate(homeLastTrainProvider),
      builder: (context, data) {
        final info = data!;
        final departure = DateTime.tryParse('${info['departure_at']}');
        final stationName = stations['${info['stop_id']}']?.name ?? '${info['stop_id']}';
        return GlassSurface(
          onTap: () => context.push('/station/${info['stop_id']}'),
          child: Row(
            children: [
              const IconBadge(icon: Icons.nightlight_rounded),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('$stationName · ${clockTime(departure)}', style: Theme.of(context).textTheme.titleMedium),
                    Text('${info['headsign'] ?? info['route_id']}', style: Theme.of(context).textTheme.bodyMedium),
                  ],
                ),
              ),
              GhostButton(
                label: 'Remind me',
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
              ),
            ],
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
      emptyIcon: Icons.history_rounded,
      onRetry: () => ref.invalidate(recentJourneysProvider),
      trailing: TextButton(onPressed: () => context.push('/journeys/history'), child: const Text('See all')),
      builder: (context, data) => Column(
        children: [
          for (final journey in data)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: GlassSurface(
                onTap: () => context.push('/planner'),
                child: Row(
                  children: [
                    IconBadge(
                      icon: switch (journey.status) {
                        'completed' => Icons.check_circle_rounded,
                        'missed' => Icons.error_rounded,
                        _ => Icons.remove_circle_rounded,
                      },
                    ),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            '${stations[journey.originStopId]?.name ?? journey.originStopId}'
                            ' → '
                            '${stations[journey.destinationStopId]?.name ?? journey.destinationStopId}',
                            style: Theme.of(context).textTheme.titleSmall,
                          ),
                          Text(journey.status, style: Theme.of(context).textTheme.bodySmall),
                        ],
                      ),
                    ),
                    const Icon(Icons.chevron_right_rounded),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
