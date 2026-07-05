import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/formatters.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/station.dart';
import '../../providers/core_providers.dart';
import '../home/home_screen.dart';
import '../shared/widgets.dart';

/// Journey planner: pick two stations, get legs/interchanges/timing, and
/// hand the plan straight to Journey Mode (interchange ids included so the
/// backend can raise interchange reminders).
class JourneyPlannerScreen extends ConsumerStatefulWidget {
  const JourneyPlannerScreen({super.key});

  @override
  ConsumerState<JourneyPlannerScreen> createState() =>
      _JourneyPlannerScreenState();
}

class _JourneyPlannerScreenState extends ConsumerState<JourneyPlannerScreen> {
  Station? _origin;
  Station? _destination;
  JourneyPlan? _plan;
  String? _error;
  bool _loading = false;

  Future<void> _pick(bool isOrigin) async {
    final station = await showModalBottomSheet<Station>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => const _StationPicker(),
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

  Future<void> _planJourney() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final plan = await ref
          .read(journeyRepositoryProvider)
          .plan(_origin!.stopId, _destination!.stopId);
      setState(() => _plan = plan);
    } on Exception {
      setState(() => _error = 'No route found between these stations.');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _startJourney() async {
    final plan = _plan!;
    final firstRide = plan.legs.where((leg) => leg.isRide).firstOrNull;
    await ref.read(journeyRepositoryProvider).start(
          origin: plan.origin.stopId,
          destination: plan.destination.stopId,
          routeId: firstRide?.routeId,
          interchangeStopIds: plan.interchangeStopIds,
        );
    ref.invalidate(activeJourneyProvider);
    if (mounted) context.go('/journey');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Plan journey')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _EndpointTile(
            label: 'From',
            station: _origin,
            onTap: () => _pick(true),
          ),
          const SizedBox(height: 8),
          _EndpointTile(
            label: 'To',
            station: _destination,
            onTap: () => _pick(false),
          ),
          const SizedBox(height: 16),
          if (_loading) const Center(child: CircularProgressIndicator()),
          if (_error != null)
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          if (_plan != null) ...[
            _PlanSummary(plan: _plan!),
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
}

class _EndpointTile extends StatelessWidget {
  const _EndpointTile({
    required this.label,
    required this.station,
    required this.onTap,
  });

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

class _PlanSummary extends StatelessWidget {
  const _PlanSummary({required this.plan});

  final JourneyPlan plan;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Wrap(
          spacing: 24,
          runSpacing: 12,
          children: [
            StatTile(
                label: 'Travel time',
                value: minutesLabel(plan.expectedTravelSeconds)),
            StatTile(label: 'Arrive', value: clockTime(plan.expectedArrivalAt)),
            StatTile(
                label: 'Interchanges', value: '${plan.interchangeCount}'),
            StatTile(
                label: 'Walking', value: distanceLabel(plan.walkingDistanceM)),
            StatTile(
                label: 'Stations', value: '${plan.remainingStations.length}'),
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
            '${distanceLabel(leg.distanceM)} · ${minutesLabel(leg.seconds)}'),
      );
    }
    return ListTile(
      leading: const Icon(Icons.directions_subway_filled),
      title: Row(
        children: [
          Flexible(
            child: LineBadge(
              label: leg.routeLongName ?? leg.routeId ?? 'Line',
              colorHex: leg.routeColor,
            ),
          ),
        ],
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

/// Offline-capable station picker (searches the cached bundle).
class _StationPicker extends ConsumerStatefulWidget {
  const _StationPicker();

  @override
  ConsumerState<_StationPicker> createState() => _StationPickerState();
}

class _StationPickerState extends ConsumerState<_StationPicker> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final stations =
        ref.watch(offlineBundleProvider).valueOrNull?.stations ?? const [];
    final matches = stations
        .where((s) => s.name.toLowerCase().contains(_query.toLowerCase()))
        .take(30)
        .toList();
    return Padding(
      padding: EdgeInsets.only(
          bottom: MediaQuery.of(context).viewInsets.bottom),
      child: SizedBox(
        height: MediaQuery.of(context).size.height * 0.7,
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: TextField(
                autofocus: true,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  hintText: 'Search stations',
                  border: OutlineInputBorder(),
                ),
                onChanged: (value) => setState(() => _query = value),
              ),
            ),
            Expanded(
              child: ListView.builder(
                itemCount: matches.length,
                itemBuilder: (_, index) {
                  final station = matches[index];
                  return ListTile(
                    leading: const Icon(Icons.place_outlined),
                    title: Text(station.name),
                    onTap: () => Navigator.of(context).pop(station),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
