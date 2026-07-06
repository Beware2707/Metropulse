import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_motion.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/live_indicator.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/section_header.dart';
import '../../data/ws_client.dart';
import '../../domain/models/eta.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import '../favourites/favourites_screen.dart';

final _lastTrainProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>?, String>((ref, stopId) async {
  return ref.watch(stationsRepositoryProvider).lastTrain(stopId);
});

final _exitsProvider = FutureProvider.autoDispose
    .family<List<Map<String, dynamic>>, String>((ref, stopId) async {
  return ref.watch(stationsRepositoryProvider).exits(stopId);
});

/// Per-train ETA for an arrivals-board row, keyed by vehicle id — the same
/// call `train_detail_screen.dart` and `live_map_screen.dart` make.
final _arrivalEtaProvider = FutureProvider.autoDispose.family<VehicleEta?, String>((ref, vehicleId) async {
  return ref.watch(trainsRepositoryProvider).eta(vehicleId);
});

/// Station detail: live arrivals (from the WS stream), lines, last train,
/// exits, and a favourite toggle.
class StationDetailScreen extends ConsumerWidget {
  const StationDetailScreen({super.key, required this.stopId});

  final String stopId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final station = ref.watch(stationIndexProvider)[stopId];
    final arrivals = ref.watch(arrivalsForStationProvider(stopId));
    final lastTrain = ref.watch(_lastTrainProvider(stopId));
    final exits = ref.watch(_exitsProvider(stopId));

    // The last-train fact only feels urgent late at night; outside that
    // window it's demoted to a single low-key row near the bottom instead of
    // a prominent "Tonight" section.
    final hour = DateTime.now().hour;
    final isNight = hour >= 20 || hour < 4;

    final lastTrainRow = MomentRow(
      leading: const IconBadge(icon: Icons.nightlight_rounded, color: AppColors.night),
      title: Text('Last train', style: Theme.of(context).textTheme.titleMedium),
      subtitle: lastTrain.when(
        data: (data) => Text(
          data == null
              ? "We don't have tonight's service info yet"
              : '${data['headsign'] ?? data['route_id']} at '
                  '${clockTime(DateTime.tryParse('${data['departure_at']}'))}',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        loading: () => const Text('…'),
        error: (_, __) => const Text('Not available offline'),
      ),
    );

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: Text(station?.name ?? stopId),
        actions: [
          _FavouriteToggle(stopId: stopId),
          const SizedBox(width: AppSpacing.sm),
        ],
      ),
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(AppSpacing.lg, 100, AppSpacing.lg, AppSpacing.xxl),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Arriving now',
                      style: Theme.of(context)
                          .textTheme
                          .headlineMedium
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                  ),
                  const LiveIndicator(),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              if (arrivals.isEmpty) const _EmptyArrivals(),
              for (final train in arrivals)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: GlassSurface(
                    onTap: () => context.push('/train/${train.id}'),
                    child: Row(
                      children: [
                        LineChip(label: train.routeShortName ?? train.lineLabel, colorHex: train.routeColor),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(train.headsign == null ? train.lineLabel : 'Towards ${train.headsign}',
                                  style: Theme.of(context).textTheme.titleMedium),
                              train.atStation
                                  ? Text('At ${train.currentStation?.name}',
                                      style: Theme.of(context).textTheme.bodySmall)
                                  : _ArrivalEtaSubtitle(vehicleId: train.id),
                            ],
                          ),
                        ),
                        const Icon(Icons.chevron_right_rounded),
                      ],
                    ),
                  ),
                ),
              if (isNight) ...[
                const SectionHeader(title: 'Tonight'),
                GlassSurface(child: lastTrainRow),
              ],
              const SectionHeader(title: 'Exits'),
              exits.when(
                data: (data) => data.isEmpty
                    ? const EmptyState(icon: Icons.exit_to_app_rounded, message: "We don't have exit info for this station yet.")
                    : MomentList(
                        children: [
                          for (final exit in data)
                            MomentRow(
                              leading: const IconBadge(icon: Icons.exit_to_app_rounded),
                              title: Text('${exit['name']}', style: Theme.of(context).textTheme.titleMedium),
                              subtitle: exit['landmarks'] is List && (exit['landmarks'] as List).isNotEmpty
                                  ? Text((exit['landmarks'] as List).join(', '),
                                      style: Theme.of(context).textTheme.bodySmall)
                                  : null,
                            ),
                        ],
                      ),
                loading: () => const SizedBox.shrink(),
                error: (_, __) => const SizedBox.shrink(),
              ),
              if (!isNight && lastTrain.hasValue && lastTrain.value != null) ...[
                const SizedBox(height: AppSpacing.xxl),
                MomentList(children: [lastTrainRow]),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// No live arrivals to show — but "no trains" reads as broken to a
/// first-time user if the WS connection simply hasn't finished (re)joining
/// yet, so this distinguishes "still connecting" from "genuinely nothing
/// scheduled".
class _EmptyArrivals extends ConsumerWidget {
  const _EmptyArrivals();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(wsStatusProvider).valueOrNull;
    final message = switch (status) {
      WsStatus.connecting => 'Connecting to live arrivals…',
      WsStatus.reconnecting => 'Reconnecting to live arrivals…',
      _ => 'No trains headed this way right now.',
    };
    return EmptyState(icon: Icons.train_rounded, message: message);
  }
}

/// Real per-row ETA for an approaching train, replacing the bare
/// "Approaching" label with an actual minutes-away figure once it resolves.
class _ArrivalEtaSubtitle extends ConsumerWidget {
  const _ArrivalEtaSubtitle({required this.vehicleId});

  final String vehicleId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final eta = ref.watch(_arrivalEtaProvider(vehicleId));
    final seconds = eta.valueOrNull?.nextStation?.etaSeconds;
    final label = seconds == null ? 'Approaching' : '${minutesLabel(seconds)} away';
    return Text(label, style: Theme.of(context).textTheme.bodySmall);
  }
}

/// The favourite-star toggle, kept optimistic: the icon flips the instant
/// you tap it, the save/remove call happens in the background, and only
/// then does the favourites provider get invalidated to reconcile with the
/// server. If the call throws, the optimistic flag reverts.
class _FavouriteToggle extends ConsumerStatefulWidget {
  const _FavouriteToggle({required this.stopId});

  final String stopId;

  @override
  ConsumerState<_FavouriteToggle> createState() => _FavouriteToggleState();
}

class _FavouriteToggleState extends ConsumerState<_FavouriteToggle> {
  bool? _optimistic;

  @override
  Widget build(BuildContext context) {
    final favourites = ref.watch(favouriteStationsProvider);
    final serverFavourite = favourites.valueOrNull?.any((f) => f['stop_id'] == widget.stopId) ?? false;
    final isFavourite = _optimistic ?? serverFavourite;

    final reduceMotion = MediaQuery.of(context).disableAnimations;

    return IconButton(
      icon: AnimatedSwitcher(
        duration: reduceMotion ? Duration.zero : AppMotion.fast,
        transitionBuilder: (child, animation) => ScaleTransition(scale: animation, child: child),
        child: Icon(
          isFavourite ? Icons.star_rounded : Icons.star_outline_rounded,
          key: ValueKey(isFavourite),
          color: isFavourite ? AppColors.warning : null,
        ),
      ),
      onPressed: () async {
        final next = !isFavourite;
        setState(() => _optimistic = next);
        final repository = ref.read(favouritesRepositoryProvider);
        try {
          if (next) {
            await repository.save(widget.stopId);
          } else {
            await repository.remove(widget.stopId);
          }
          ref.invalidate(favouriteStationsProvider);
        } catch (_) {
          if (mounted) setState(() => _optimistic = !next);
        }
      },
    );
  }
}
