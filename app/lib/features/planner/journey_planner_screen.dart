import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../data/repositories.dart';
import '../../domain/fare.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/station.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart';
import '../shared/station_search_sheet.dart';
import '../shared/widgets.dart';

/// Journey planner: pick two stations, choose a route preference, get a
/// visualised route with legs/interchanges/fare/timing, and hand the plan
/// straight to Journey Mode (interchange ids + the full plan snapshot
/// included, so Journey Mode's timetable simulation and interchange
/// reminders both work immediately, even offline-for-progress).
class JourneyPlannerScreen extends ConsumerStatefulWidget {
  const JourneyPlannerScreen({super.key, this.initialOriginId, this.initialDestinationId});

  final String? initialOriginId;
  final String? initialDestinationId;

  @override
  ConsumerState<JourneyPlannerScreen> createState() => _JourneyPlannerScreenState();
}

class _JourneyPlannerScreenState extends ConsumerState<JourneyPlannerScreen> {
  Station? _origin;
  Station? _destination;
  RoutePreference _preference = RoutePreference.fastest;
  bool _wheelchairRequested = false;
  JourneyPlan? _plan;
  String? _error;
  bool _loading = false;
  bool _resolvedInitialStations = false;

  @override
  Widget build(BuildContext context) {
    // Resolve id -> Station once the offline bundle is available, without
    // blocking first frame on it.
    if (!_resolvedInitialStations) {
      final stations = ref.watch(stationIndexProvider);
      if (stations.isNotEmpty) {
        _resolvedInitialStations = true;
        _origin ??= stations[widget.initialOriginId];
        _destination ??= stations[widget.initialDestinationId];
        if (_origin != null && _destination != null) {
          WidgetsBinding.instance.addPostFrameCallback((_) => _planJourney());
        }
      }
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Plan journey'),
        actions: [
          IconButton(
            tooltip: 'Swap origin and destination',
            icon: const Icon(Icons.swap_vert),
            onPressed: _origin == null || _destination == null ? null : _swap,
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _EndpointTile(label: 'From', station: _origin, onTap: () => _pick(true)),
          const SizedBox(height: 8),
          _EndpointTile(label: 'To', station: _destination, onTap: () => _pick(false)),
          const SizedBox(height: 16),
          _PreferenceSelector(
            preference: _preference,
            wheelchairRequested: _wheelchairRequested,
            onPreferenceChanged: (value) {
              setState(() => _preference = value);
              _planJourney();
            },
            onWheelchairToggled: (value) => setState(() => _wheelchairRequested = value),
          ),
          const SizedBox(height: 16),
          if (_loading) const Center(child: CircularProgressIndicator()),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(_error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          if (_plan != null) ...[
            _PlanSummary(plan: _plan!, onPin: _pinJourney),
            const SizedBox(height: 12),
            _RouteVisualization(plan: _plan!),
            const SizedBox(height: 12),
            for (final leg in _plan!.legs) _LegTile(leg: leg),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _startJourney,
              icon: const Icon(Icons.navigation_outlined),
              label: const Text('Start journey mode'),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> _pick(bool isOrigin) async {
    final station = await showModalBottomSheet<Station>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => StationSearchSheet(title: 'Choose ${isOrigin ? 'origin' : 'destination'}'),
    );
    if (station == null) return;
    setState(() {
      if (isOrigin) {
        _origin = station;
      } else {
        _destination = station;
      }
      _plan = null;
      _error = null;
    });
    if (_origin != null && _destination != null) await _planJourney();
  }

  void _swap() {
    setState(() {
      final origin = _origin;
      _origin = _destination;
      _destination = origin;
      _plan = null;
    });
    _planJourney();
  }

  Future<void> _planJourney() async {
    if (_origin == null || _destination == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final plan = await ref.read(journeyRepositoryProvider).plan(
            _origin!.stopId,
            _destination!.stopId,
            preference: _preference,
          );
      if (!mounted) return;
      setState(() => _plan = plan);
    } on Exception {
      if (!mounted) return;
      setState(() => _error = 'No route found between these stations.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pinJourney() async {
    final origin = _origin!;
    final destination = _destination!;
    final label = await showDialog<String>(
      context: context,
      builder: (dialogContext) {
        final controller = TextEditingController(text: '${origin.name} → ${destination.name}');
        return AlertDialog(
          title: const Text('Pin this journey'),
          content: TextField(controller: controller, autofocus: true),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(controller.text.trim()),
              child: const Text('Pin'),
            ),
          ],
        );
      },
    );
    if (label == null || label.isEmpty) return;
    await ref.read(localStoreProvider).addPinnedJourney(
          originStopId: origin.stopId,
          destinationStopId: destination.stopId,
          label: label,
        );
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Journey pinned to Favourites.')));
    }
  }

  Future<void> _startJourney() async {
    final plan = _plan!;
    final firstRide = plan.legs.where((leg) => leg.isRide).firstOrNull;
    final repository = ref.read(journeyRepositoryProvider);
    final journey = await repository.start(
      origin: plan.origin.stopId,
      destination: plan.destination.stopId,
      routeId: firstRide?.routeId,
      interchangeStopIds: plan.interchangeStopIds,
    );

    // Persist the plan snapshot + start time so Journey Mode's GTFS-
    // timetable simulation survives backgrounding and a full restart, and
    // the coach recommendation so it can guide boarding immediately.
    final coach = await repository.coachRecommendation(
      origin: plan.origin.stopId,
      destination: plan.destination.stopId,
      routeId: firstRide?.routeId,
      directionId: firstRide?.directionId,
    );
    await ref.read(localStoreProvider).saveJourneyContext(journey.id, {
      'plan': plan.toJson(),
      'started_at': DateTime.now().toIso8601String(),
      'total_stations': plan.remainingStations.length,
      'interchange_stop_ids': plan.interchangeStopIds,
      'route_long_name': firstRide?.routeLongName,
      'route_color': firstRide?.routeColor,
      'platform_hint': firstRide?.platformHint,
      'recommended_coach': coach?['recommended_coach'],
    });

    ref
      ..invalidate(activeJourneyProvider)
      ..invalidate(recentJourneysProvider);
    if (mounted) context.go('/journey');
  }
}

class _EndpointTile extends StatelessWidget {
  const _EndpointTile({required this.label, required this.station, required this.onTap});

  final String label;
  final Station? station;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: Icon(label == 'From' ? Icons.trip_origin : Icons.flag_outlined),
        title: Text(station?.name ?? 'Choose $label station'),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}

class _PreferenceSelector extends StatelessWidget {
  const _PreferenceSelector({
    required this.preference,
    required this.wheelchairRequested,
    required this.onPreferenceChanged,
    required this.onWheelchairToggled,
  });

  final RoutePreference preference;
  final bool wheelchairRequested;
  final ValueChanged<RoutePreference> onPreferenceChanged;
  final ValueChanged<bool> onWheelchairToggled;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Wrap(
          spacing: 8,
          children: [
            for (final (value, label) in const [
              (RoutePreference.fastest, 'Fastest'),
              (RoutePreference.fewerTransfers, 'Fewer interchanges'),
              (RoutePreference.lessWalking, 'Less walking'),
            ])
              ChoiceChip(
                label: Text(label),
                selected: preference == value,
                onSelected: (_) => onPreferenceChanged(value),
              ),
            FilterChip(
              label: const Text('Wheelchair-friendly'),
              selected: wheelchairRequested,
              onSelected: onWheelchairToggled,
            ),
          ],
        ),
        if (wheelchairRequested)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              "Wheelchair-accessible routing isn't available for this network "
              'yet — showing the standard route instead.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: Theme.of(context).colorScheme.error),
            ),
          ),
      ],
    );
  }
}

class _PlanSummary extends StatelessWidget {
  const _PlanSummary({required this.plan, required this.onPin});

  final JourneyPlan plan;
  final VoidCallback onPin;

  @override
  Widget build(BuildContext context) {
    final fare = estimateFare(plan);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Wrap(
                    spacing: 24,
                    runSpacing: 12,
                    children: [
                      StatTile(
                          label: 'Travel time',
                          value: minutesLabel(plan.expectedTravelSeconds)),
                      StatTile(label: 'Arrive', value: clockTime(plan.expectedArrivalAt)),
                      StatTile(label: 'Fare (est.)', value: '₹${fare.rupees}'),
                      StatTile(
                          label: 'Interchanges', value: '${plan.interchangeCount}'),
                      StatTile(
                          label: 'Walking', value: distanceLabel(plan.walkingDistanceM)),
                    ],
                  ),
                ),
                IconButton(
                  tooltip: 'Pin this journey',
                  icon: const Icon(Icons.push_pin_outlined),
                  onPressed: onPin,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// A simple, legible route visualisation: a coloured vertical line per ride
/// leg with its stations, and a dashed connector for walking transfers.
class _RouteVisualization extends StatelessWidget {
  const _RouteVisualization({required this.plan});

  final JourneyPlan plan;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final leg in plan.legs)
              if (leg.isRide)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    children: [
                      Container(
                        width: 10,
                        height: 10,
                        decoration: BoxDecoration(
                          color: routeColor(leg.routeColor),
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Container(
                          height: 4,
                          decoration: BoxDecoration(
                            color: routeColor(leg.routeColor),
                            borderRadius: BorderRadius.circular(2),
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text('${(leg.stations?.length ?? 1) - 1} stops',
                          style: theme.textTheme.labelSmall),
                    ],
                  ),
                )
              else
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Row(
                    children: [
                      Icon(Icons.more_vert, size: 16, color: theme.colorScheme.outline),
                      const SizedBox(width: 8),
                      Text('Walk ${distanceLabel(leg.distanceM)}',
                          style: theme.textTheme.labelSmall
                              ?.copyWith(color: theme.colorScheme.outline)),
                    ],
                  ),
                ),
          ],
        ),
      ),
    );
  }
}

class _LegTile extends StatelessWidget {
  const _LegTile({required this.leg});

  final JourneyLeg leg;

  @override
  Widget build(BuildContext context) {
    if (!leg.isRide) {
      return ListTile(
        leading: const Icon(Icons.directions_walk),
        title: Text('Walk to ${leg.alight.name}'),
        subtitle: Text(
          '${distanceLabel(leg.distanceM)} · about ${minutesLabel(leg.seconds)} on foot',
        ),
      );
    }
    return ListTile(
      leading: const Icon(Icons.directions_subway_filled),
      title: LineBadge(
        label: leg.routeLongName ?? leg.routeId ?? 'Line',
        colorHex: leg.routeColor,
      ),
      subtitle: Text(
        '${leg.board.name} → ${leg.alight.name}'
        '${leg.platformHint != null ? '  ·  ${leg.platformHint}' : ''}\n'
        '${(leg.stations?.length ?? 1) - 1} stops · ${minutesLabel(leg.seconds)}',
      ),
      isThreeLine: true,
    );
  }
}
