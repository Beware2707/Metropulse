import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters.dart';
import '../../core/l10n_ext.dart';
import '../../domain/companion_messages.dart';
import '../../domain/journey_progress.dart';
import '../../domain/models/journey.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart';
import '../shared/widgets.dart';
import 'journey_mode_providers.dart';

/// The best exit at the destination for this line/direction (fetched once
/// per key; works even without a live vehicle, since exits are keyed by
/// station and only optionally refined by route/direction).
final _exitProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>?, (String, String?, int?)>((ref, key) async {
  return ref
      .watch(journeyRepositoryProvider)
      .bestExit(key.$1, routeId: key.$2, directionId: key.$3);
});

/// Journey Mode: the persistent live trip card — MetroPulse's flagship
/// screen. Everything on it is driven by [JourneyProgressSnapshot], which is
/// itself sourced from a live WS-tracked vehicle when one is bound and fresh,
/// falling back to a GTFS-timetable simulation otherwise (see
/// `journey_mode_providers.dart`). No fake GPS is ever synthesised.
///
/// Recovery model: the server owns the journey session (auto-complete,
/// missed-stop, interchange and delay detection); Hive holds the
/// plan-derived extras (coach, interchanges, the full plan snapshot) needed
/// to rebuild the timetable simulation after backgrounding or a full
/// restart; the WebSocket stream drives every live-vehicle element.
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
    final journeyContext = ref.watch(journeyContextProvider(journey.id));
    final snapshot = ref.watch(journeyProgressProvider(journey));

    // Best-effort: reinforce the in-app banner with a real backend push
    // once a live vehicle is bound. Fire-and-forget; result unused here.
    if (journey.vehicleId != null) {
      ref.watch(destinationAlertCreationProvider(
        (journey.id, journey.vehicleId!, journey.destinationStopId),
      ));
    }

    final destinationLeg = journeyContext?.plan?.legs
        .where((leg) => leg.isRide && leg.alight.stopId == journey.destinationStopId)
        .lastOrNull;
    final exit = ref
        .watch(_exitProvider((
          journey.destinationStopId,
          destinationLeg?.routeId,
          destinationLeg?.directionId,
        )))
        .valueOrNull;
    final exitName = exit == null ? null : '${exit['name']}';

    final origin = stations[journey.originStopId]?.name ?? journey.originStopId;
    final destination =
        stations[journey.destinationStopId]?.name ?? journey.destinationStopId;

    final message = buildCompanionMessage(
      arrived: snapshot?.arrived ?? false,
      arrivingSoon: snapshot?.arrivingSoon ?? false,
      exitName: exitName,
      approachingInterchange: snapshot?.approachingInterchange ?? false,
      interchangeStationName: snapshot?.interchangeStationName,
      justBoarded: snapshot?.justBoarded ?? false,
      recommendedCoach: journeyContext?.recommendedCoach,
      platformHint: journeyContext?.platformHint,
      nextStationName: snapshot?.nextStationName,
    );

    final theme = Theme.of(context);
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 640),
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (message != null) _CompanionBanner(message: message),
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
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: LinearProgressIndicator(
                        value: snapshot?.fractionComplete,
                        minHeight: 8,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            snapshot?.remainingStations == null
                                ? '–'
                                : '${snapshot!.remainingStations} station(s) remaining',
                            style: theme.textTheme.labelMedium,
                          ),
                        ),
                        if (snapshot != null)
                          Text(
                            snapshot.source == JourneyProgressSource.liveVehicle
                                ? 'LIVE TRACKING'
                                : 'ESTIMATED FROM TIMETABLE',
                            style: theme.textTheme.labelSmall?.copyWith(
                              color: theme.colorScheme.outline,
                              letterSpacing: 0.5,
                            ),
                          ),
                      ],
                    ),
                    const Divider(height: 32),
                    Wrap(
                      spacing: 24,
                      runSpacing: 16,
                      children: [
                        StatTile(
                          label: context.t.journeyBoard,
                          value: journeyContext?.routeLongName ?? '–',
                        ),
                        if (journeyContext?.recommendedCoach != null)
                          StatTile(
                            label: context.t.journeyCoach,
                            value: '${journeyContext!.recommendedCoach! + 1}',
                          ),
                        if (exitName != null)
                          StatTile(label: context.t.journeyExit, value: exitName),
                        StatTile(
                          label: context.t.journeyTimeRemaining,
                          value: snapshot?.etaToDestination == null
                              ? '–'
                              : minutesLabel(
                                  snapshot!.etaToDestination!.inSeconds.toDouble()),
                        ),
                        StatTile(
                          label: context.t.journeyStationsRemaining,
                          value: snapshot?.remainingStations?.toString() ?? '–',
                        ),
                        if (snapshot?.delaySeconds != null &&
                            snapshot!.delaySeconds! > 120)
                          StatTile(
                            label: context.t.journeyRunningLate,
                            value: minutesLabel(snapshot.delaySeconds),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
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

class _CompanionBanner extends StatelessWidget {
  const _CompanionBanner({required this.message});

  final CompanionMessage message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (color, icon) = switch (message.kind) {
      CompanionMessageKind.arrived => (scheme.primaryContainer, Icons.flag_circle_outlined),
      CompanionMessageKind.arriving =>
        (scheme.primaryContainer, Icons.notifications_active_outlined),
      CompanionMessageKind.interchange =>
        (scheme.tertiaryContainer, Icons.transfer_within_a_station),
      CompanionMessageKind.boarding => (scheme.secondaryContainer, Icons.directions_subway_filled),
      CompanionMessageKind.nextStation => (scheme.surfaceContainerHighest, Icons.arrow_forward),
    };
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Card(
        color: color,
        child: ListTile(
          leading: Icon(icon),
          title: Text(message.text, style: const TextStyle(fontWeight: FontWeight.w600)),
        ),
      ),
    );
  }
}
