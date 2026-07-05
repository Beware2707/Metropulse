import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters.dart';
import '../../core/l10n_ext.dart';
import '../../core/theme.dart';
import '../../domain/journey_progress.dart';
import '../../domain/models/eta.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/train.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import '../home/home_providers.dart';
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
/// State model:
/// - the *server* owns the journey session (auto-complete, missed-stop,
///   interchange and delay notifications) — GET /me/journeys/current is the
///   source of truth, so backgrounding or a full restart recovers cleanly;
/// - *Hive* keeps the plan-derived extras (coach, interchanges, totals)
///   keyed by journey id, written when the journey starts;
/// - the *WebSocket* stream drives every live element on screen.
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
        error: (error, _) =>
            Center(child: Text('Could not load journey: $error')),
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
          Text(context.t.journeyNoJourney),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: () => context.go('/planner'),
            child: Text(context.t.journeyPlanCta),
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
    final store = ref.watch(localStoreProvider);
    final journeyContext = store.journeyContext(journey.id) ?? const {};

    final origin =
        stations[journey.originStopId]?.name ?? journey.originStopId;
    final destination = stations[journey.destinationStopId]?.name ??
        journey.destinationStopId;

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
    final exit = ref
        .watch(_exitProvider((
          journey.destinationStopId,
          train?.routeId,
          train?.directionId,
        )))
        .valueOrNull;

    final progress = JourneyProgress(
      totalStations: (journeyContext['total_stations'] as num?)?.toInt() ??
          (train?.remainingStations.length ?? 0),
      remainingToDestination: train == null
          ? null
          : remainingToDestination(
              [for (final s in train.remainingStations) s.stopId],
              journey.destinationStopId,
            ),
    );
    final interchangeIds = [
      for (final id
          in (journeyContext['interchange_stop_ids'] as List<dynamic>? ??
              const []))
        '$id',
    ];
    final approachingInterchange = train?.nextStation != null &&
        interchangeIds.contains(train!.nextStation!.stopId);

    final theme = Theme.of(context);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (progress.arrivingSoon)
              _ReminderBanner(
                icon: Icons.notifications_active_outlined,
                color: theme.colorScheme.primaryContainer,
                text: context.t.journeyArrivingSoon,
              ),
            if (approachingInterchange)
              _ReminderBanner(
                icon: Icons.transfer_within_a_station,
                color: theme.colorScheme.tertiaryContainer,
                text: context.t
                    .journeyInterchangeSoon(train.nextStation!.name),
              ),
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
                    const SizedBox(height: 16),
                    // Live progress: fills as stations are passed.
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: LinearProgressIndicator(
                        value: progress.fraction,
                        minHeight: 8,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(progress.label,
                        style: theme.textTheme.labelMedium),
                    const Divider(height: 32),
                    Wrap(
                      spacing: 24,
                      runSpacing: 16,
                      children: [
                        StatTile(
                          label: context.t.journeyBoard,
                          value: train?.lineLabel ??
                              '${journeyContext['route_long_name'] ?? '–'}',
                        ),
                        if (journeyContext['recommended_coach'] != null)
                          StatTile(
                            label: context.t.journeyCoach,
                            value:
                                '${(journeyContext['recommended_coach'] as num).toInt() + 1}',
                          ),
                        if (exit != null)
                          StatTile(
                              label: context.t.journeyExit,
                              value: '${exit['name']}'),
                        StatTile(
                          label: context.t.journeyTimeRemaining,
                          value: minutesLabel(destinationEta?.etaSeconds),
                        ),
                        StatTile(
                          label: context.t.journeyStationsRemaining,
                          value:
                              progress.remainingToDestination?.toString() ??
                                  '–',
                        ),
                        if (eta?.delaySeconds != null &&
                            eta!.delaySeconds! > 120)
                          StatTile(
                            label: context.t.journeyRunningLate,
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
                    child: Text(context.t.journeyAbandon),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton(
                    onPressed: () => _end(context, ref, completed: true),
                    child: Text(context.t.journeyArrived),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _end(BuildContext context, WidgetRef ref,
      {required bool completed}) async {
    await ref
        .read(journeyRepositoryProvider)
        .end(journey.id, completed: completed);
    await ref.read(localStoreProvider).clearJourneyContext();
    ref
      ..invalidate(activeJourneyProvider)
      ..invalidate(recentJourneysProvider);
    if (context.mounted) context.go('/');
  }
}

class _ReminderBanner extends StatelessWidget {
  const _ReminderBanner({
    required this.icon,
    required this.color,
    required this.text,
  });

  final IconData icon;
  final Color color;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: color,
      child: ListTile(
        leading: Icon(icon),
        title: Text(text),
      ),
    );
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
          train.headsign == null
              ? train.lineLabel
              : 'Towards ${train.headsign}',
          style: theme.textTheme.bodySmall,
        ),
        trailing: train.isStale
            ? const Icon(Icons.signal_wifi_off, size: 18)
            : const Icon(Icons.rss_feed, size: 18, color: Colors.green),
      ),
    );
  }
}
