import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/live_indicator.dart';
import '../../core/widgets/section_header.dart';
import '../../core/widgets/stat_pill.dart';
import '../../domain/models/eta.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';

final _etaProvider = FutureProvider.autoDispose
    .family<VehicleEta?, (String, String)>((ref, key) async {
  return ref.watch(trainsRepositoryProvider).eta(key.$1);
});

/// Full train detail: live state plus per-station ETAs down the line.
class TrainDetailScreen extends ConsumerWidget {
  const TrainDetailScreen({super.key, required this.vehicleId});

  final String vehicleId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final train = ref.watch(liveTrainProvider(vehicleId));
    final eta = train == null
        ? null
        : ref.watch(_etaProvider((vehicleId, train.vehicle.timestamp.toIso8601String()))).valueOrNull;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: Text(train?.lineLabel ?? 'Train'),
        actions: const [Padding(padding: EdgeInsets.only(right: 16), child: Center(child: LiveIndicator()))],
      ),
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: train == null
              ? const Center(child: Text("We've lost track of this train — it may have finished its trip."))
              : ListView(
                  padding: const EdgeInsets.fromLTRB(AppSpacing.lg, 100, AppSpacing.lg, AppSpacing.xxl),
                  children: [
                    GlassSurface(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          LineChip(label: train.lineLabel, colorHex: train.routeColor),
                          const SizedBox(height: AppSpacing.md),
                          if (train.headsign != null)
                            Text('Towards ${train.headsign}', style: Theme.of(context).textTheme.headlineSmall),
                          const SizedBox(height: AppSpacing.lg),
                          Wrap(
                            spacing: AppSpacing.md,
                            runSpacing: AppSpacing.md,
                            children: [
                              StatPill(
                                icon: Icons.train_rounded,
                                label: 'Status',
                                value: train.atStation ? 'At ${train.currentStation?.name ?? '…'}' : 'Moving',
                              ),
                              if (train.destination != null)
                                StatPill(icon: Icons.flag_rounded, label: 'Destination', value: train.destination!.name),
                              if (eta?.delaySeconds != null)
                                StatPill(
                                  icon: Icons.schedule_rounded,
                                  label: 'Schedule',
                                  value: eta!.delaySeconds! > 60 ? '${minutesLabel(eta.delaySeconds)} late' : 'On time',
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),
                    const SectionHeader(title: 'Upcoming stations'),
                    if (eta == null || eta.stations.isEmpty)
                      const EmptyState(icon: Icons.info_rounded, message: "We don't have arrival times for this train yet.")
                    else
                      for (final station in eta.stations)
                        Padding(
                          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                          child: GlassSurface(
                            onTap: () => context.push('/station/${station.stopId}'),
                            child: Row(
                              children: [
                                Container(
                                  width: 10,
                                  height: 10,
                                  decoration: BoxDecoration(
                                    color: routeColor(train.routeColor, train.lineLabel),
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: AppSpacing.md),
                                Expanded(child: Text(station.stopName, style: Theme.of(context).textTheme.titleMedium)),
                                Text(minutesLabel(station.etaSeconds),
                                    style: Theme.of(context).textTheme.titleMedium),
                              ],
                            ),
                          ),
                        ),
                  ],
                ),
        ),
      ),
    );
  }
}
