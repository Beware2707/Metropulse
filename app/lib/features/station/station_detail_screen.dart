import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import '../favourites/favourites_screen.dart';
import '../shared/widgets.dart';

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
    final isFavourite = favourites.valueOrNull
            ?.any((f) => f['stop_id'] == stopId) ??
        false;

    return Scaffold(
      appBar: AppBar(
        title: Text(station?.name ?? stopId),
        actions: [
          IconButton(
            icon: Icon(isFavourite ? Icons.star : Icons.star_outline),
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
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(
            children: [
              Text('Arriving now', style: Theme.of(context).textTheme.titleMedium),
              const Spacer(),
              const LiveIndicator(),
            ],
          ),
          const SizedBox(height: 8),
          if (arrivals.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text('No trains currently approaching this station.'),
              ),
            ),
          for (final train in arrivals)
            Card(
              child: ListTile(
                leading: LineBadge(
                    label: train.routeShortName ?? train.lineLabel,
                    colorHex: train.routeColor),
                title: Text(train.headsign == null
                    ? train.lineLabel
                    : 'Towards ${train.headsign}'),
                subtitle: Text(train.atStation
                    ? 'At ${train.currentStation?.name}'
                    : 'Approaching'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => context.push('/train/${train.id}'),
              ),
            ),
          const SizedBox(height: 16),
          Text('Tonight', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.nightlight_outlined),
              title: const Text('Last train'),
              subtitle: lastTrain.when(
                data: (data) => Text(data == null
                    ? 'No service information'
                    : '${data['headsign'] ?? data['route_id']} at '
                        '${clockTime(DateTime.tryParse('${data['departure_at']}'))}'),
                loading: () => const Text('...'),
                error: (_, __) => const Text('Unavailable offline'),
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('Exits', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          exits.when(
            data: (data) => data.isEmpty
                ? const Card(
                    child: Padding(
                      padding: EdgeInsets.all(16),
                      child: Text('No exit information for this station yet.'),
                    ),
                  )
                : Column(
                    children: [
                      for (final exit in data)
                        Card(
                          child: ListTile(
                            leading: const Icon(Icons.exit_to_app),
                            title: Text('${exit['name']}'),
                            subtitle: exit['landmarks'] is List &&
                                    (exit['landmarks'] as List).isNotEmpty
                                ? Text((exit['landmarks'] as List).join(', '))
                                : null,
                          ),
                        ),
                    ],
                  ),
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
          ),
        ],
      ),
    );
  }
}
