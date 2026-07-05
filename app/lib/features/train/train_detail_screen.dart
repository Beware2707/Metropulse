import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../domain/models/eta.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import '../shared/widgets.dart';

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
        : ref
            .watch(_etaProvider(
                (vehicleId, train.vehicle.timestamp.toIso8601String())))
            .valueOrNull;

    return Scaffold(
      appBar: AppBar(
        title: Text(train?.lineLabel ?? 'Train'),
        actions: const [
          Padding(
              padding: EdgeInsets.only(right: 16),
              child: Center(child: LiveIndicator())),
        ],
      ),
      body: train == null
          ? const Center(child: Text('This train is no longer tracked.'))
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        LineBadge(
                            label: train.lineLabel,
                            colorHex: train.routeColor),
                        const SizedBox(height: 12),
                        if (train.headsign != null)
                          Text('Towards ${train.headsign}',
                              style: Theme.of(context).textTheme.titleLarge),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 24,
                          runSpacing: 12,
                          children: [
                            StatTile(
                              label: 'Status',
                              value: train.atStation
                                  ? 'At ${train.currentStation?.name ?? '…'}'
                                  : 'Moving',
                            ),
                            if (train.destination != null)
                              StatTile(
                                  label: 'Destination',
                                  value: train.destination!.name),
                            if (eta?.delaySeconds != null)
                              StatTile(
                                label: 'Schedule',
                                value: eta!.delaySeconds! > 60
                                    ? '${minutesLabel(eta.delaySeconds)} late'
                                    : 'On time',
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Text('Upcoming stations',
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                if (eta == null || eta.stations.isEmpty)
                  const Card(
                    child: Padding(
                      padding: EdgeInsets.all(16),
                      child: Text('Arrival times unavailable.'),
                    ),
                  )
                else
                  for (final station in eta.stations)
                    ListTile(
                      leading: Icon(Icons.circle,
                          size: 12, color: routeColor(train.routeColor)),
                      title: Text(station.stopName),
                      trailing: Text(
                        minutesLabel(station.etaSeconds),
                        style: Theme.of(context)
                            .textTheme
                            .titleMedium
                            ?.copyWith(fontWeight: FontWeight.w700),
                      ),
                      onTap: () => context.push('/station/${station.stopId}'),
                    ),
              ],
            ),
    );
  }
}
