import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/live_indicator.dart';
import '../../core/widgets/section_header.dart';
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
    final favourites = ref.watch(favouriteStationsProvider);
    final isFavourite = favourites.valueOrNull?.any((f) => f['stop_id'] == stopId) ?? false;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: Text(station?.name ?? stopId),
        actions: [
          IconButton(
            icon: Icon(isFavourite ? Icons.star_rounded : Icons.star_outline_rounded,
                color: isFavourite ? AppColors.warning : null),
            onPressed: () async {
              final repository = ref.read(favouritesRepositoryProvider);
              if (isFavourite) {
                await repository.remove(stopId);
              } else {
                await repository.save(stopId);
              }
              ref.invalidate(favouriteStationsProvider);
            },
          ),
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
                  Expanded(child: Text('Arriving now', style: Theme.of(context).textTheme.headlineSmall)),
                  const LiveIndicator(),
                ],
              ),
              const SizedBox(height: AppSpacing.md),
              if (arrivals.isEmpty)
                const EmptyState(icon: Icons.train_rounded, message: 'No trains headed this way right now.'),
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
                              Text(train.atStation ? 'At ${train.currentStation?.name}' : 'Approaching',
                                  style: Theme.of(context).textTheme.bodySmall),
                            ],
                          ),
                        ),
                        const Icon(Icons.chevron_right_rounded),
                      ],
                    ),
                  ),
                ),
              const SectionHeader(title: 'Tonight'),
              GlassSurface(
                child: Row(
                  children: [
                    const IconBadge(icon: Icons.nightlight_rounded),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Last train', style: Theme.of(context).textTheme.titleMedium),
                          lastTrain.when(
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
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SectionHeader(title: 'Exits'),
              exits.when(
                data: (data) => data.isEmpty
                    ? const EmptyState(icon: Icons.exit_to_app_rounded, message: "We don't have exit info for this station yet.")
                    : Column(
                        children: [
                          for (final exit in data)
                            Padding(
                              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                              child: GlassSurface(
                                child: Row(
                                  children: [
                                    const IconBadge(icon: Icons.exit_to_app_rounded),
                                    const SizedBox(width: AppSpacing.md),
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text('${exit['name']}', style: Theme.of(context).textTheme.titleMedium),
                                          if (exit['landmarks'] is List && (exit['landmarks'] as List).isNotEmpty)
                                            Text((exit['landmarks'] as List).join(', '),
                                                style: Theme.of(context).textTheme.bodySmall),
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                        ],
                      ),
                loading: () => const SizedBox.shrink(),
                error: (_, __) => const SizedBox.shrink(),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
