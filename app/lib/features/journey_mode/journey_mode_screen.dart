import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../domain/models/eta.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/train.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import '../home/home_screen.dart';
import '../shared/widgets.dart';

/// ETA for the tracked train, re-fetched only when its WS state changes
/// (the feed timestamp is part of the provider key — event-driven, no polling).
final _journeyEtaProvider = FutureProvider.autoDispose
    .family<VehicleEta?, (String, String)>((ref, key) async {
  return ref.watch(trainsRepositoryProvider).eta(key.$1);
});

/// The best exit at the destination for this line/direction (fetched once).
final _exitProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>?, (String, String?, int?)>((ref, key) async {
  return ref
      .watch(journeyRepositoryProvider)
      .bestExit(key.$1, routeId: key.$2, directionId: key.$3);
});

/// Journey Mode: the persistent live trip card.
///
/// Everything on screen updates from the WebSocket stream; server-side the
/// journey session auto-completes on arrival and raises interchange /
/// missed-stop / delay notifications.
class JourneyModeScreen extends ConsumerWidget {
  const JourneyModeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final journeyAsync = ref.watch(activeJourneyProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Journey mode'),
        actions: const [
          Padding(
              padding: EdgeInsets.only(right: 16),
              child: Center(child: LiveIndicator())),
        ],
      ),
      body: journeyAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('Could not load journey: $error')),
        data: (journey) => journey == null
            ? const _NoJourney()
            : _JourneyView(journey: journey),
      ),
    );
  }
}

class _NoJourney extends StatelessWidget {
  const _NoJourney();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.route_outlined, size: 56),
          const SizedBox(height: 12),
          const Text('No journey in progress'),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: () => context.go('/planner'),
            child: const Text('Plan a journey'),
          ),
        ],
      ),
    );
  }
}

class _JourneyView extends ConsumerWidget {
  const _JourneyView({required this.journey});

  final Journey journey;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stations = ref.watch(stationIndexProvider);
    final origin = stations[journey.originStopId]?.name ?? journey.originStopId;
    final destination =
        stations[journey.destinationStopId]?.name ?? journey.destinationStopId;

    final train = journey.vehicleId == null
        ? null
        : ref.watch(liveTrainProvider(journey.vehicleId!));

    final eta = journey.vehicleId == null
        ? null
        : ref
            .watch(_journeyEtaProvider((
              journey.vehicleId!,
              train?.vehicle.timestamp.toIso8601String() ?? '',
            )))
            .valueOrNull;

    final destinationEta = eta?.stations
        .where((s) => s.stopId == journey.destinationStopId)
        .firstOrNull;
    final remainingToDestination = _remainingToDestination(train, journey);
    final exit = ref
        .watch(_exitProvider((
          journey.destinationStopId,
          train?.routeId,
          train?.directionId,
        )))
        .valueOrNull;

    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(origin, style: theme.textTheme.titleLarge),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Icon(Icons.arrow_downward,
                      color: theme.colorScheme.outline),
                ),
                Text(destination,
                    style: theme.textTheme.titleLarge
                        ?.copyWith(fontWeight: FontWeight.w800)),
                const Divider(height: 32),
                Wrap(
                  spacing: 24,
                  runSpacing: 16,
                  children: [
                    if (train != null)
                      StatTile(label: 'Board', value: train.lineLabel),
                    if (exit != null)
                      StatTile(label: 'Exit', value: '${exit['name']}'),
                    StatTile(
                      label: 'Time remaining',
                      value: minutesLabel(destinationEta?.etaSeconds),
                    ),
                    StatTile(
                      label: 'Stations remaining',
                      value: remainingToDestination?.toString() ?? '–',
                    ),
                    if (eta?.delaySeconds != null &&
                        eta!.delaySeconds! > 120)
                      StatTile(
                        label: 'Running late',
                        value: minutesLabel(eta.delaySeconds),
                      ),
                  ],
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        if (train != null) _LiveTrainCard(train: train),
        const SizedBox(height: 24),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                onPressed: () => _end(context, ref, completed: false),
                child: const Text('Abandon'),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: FilledButton(
                onPressed: () => _end(context, ref, completed: true),
                child: const Text('I have arrived'),
              ),
            ),
          ],
        ),
      ],
    );
  }

  /// Stations left strictly before (and including) the destination.
  int? _remainingToDestination(Train? train, Journey journey) {
    if (train == null) return null;
    final remaining = train.remainingStations;
    final index = remaining
        .indexWhere((station) => station.stopId == journey.destinationStopId);
    if (index >= 0) return index + 1;
    return remaining.isEmpty ? 0 : null; // interchange leg: count unknown
  }

  Future<void> _end(BuildContext context, WidgetRef ref,
      {required bool completed}) async {
    await ref
        .read(journeyRepositoryProvider)
        .end(journey.id, completed: completed);
    ref.invalidate(activeJourneyProvider);
    if (context.mounted) context.go('/');
  }
}

class _LiveTrainCard extends StatelessWidget {
  const _LiveTrainCard({required this.train});

  final Train train;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: ListTile(
        leading: Icon(Icons.directions_subway_filled,
            color: routeColor(train.routeColor)),
        title: Text(
          train.atStation
              ? 'At ${train.currentStation?.name ?? '…'}'
              : 'Next: ${train.nextStation?.name ?? '…'}',
        ),
        subtitle: Text(
          train.headsign == null ? train.lineLabel : 'Towards ${train.headsign}',
          style: theme.textTheme.bodySmall,
        ),
        trailing: train.isStale
            ? const Icon(Icons.signal_wifi_off, size: 18)
            : const Icon(Icons.rss_feed, size: 18, color: Colors.green),
      ),
    );
  }
}
