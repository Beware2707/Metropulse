import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/reveal_animations.dart';
import '../../data/repositories.dart';
import '../../domain/fare.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/station.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart';
import '../shared/station_search_sheet.dart';

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
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Plan journey'),
        actions: [
          IconPillButton(
            icon: Icons.swap_vert_rounded,
            tooltip: 'Swap origin and destination',
            onPressed: _origin == null || _destination == null ? null : _swap,
          ),
          const SizedBox(width: AppSpacing.lg),
        ],
      ),
      body: AmbientBackground(
        intensity: 0.6,
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(AppSpacing.lg, 100, AppSpacing.lg, 48),
            children: [
              _EndpointTile(
                label: 'From',
                icon: Icons.trip_origin_rounded,
                station: _origin,
                onTap: () => _pick(true),
              ),
              const SizedBox(height: AppSpacing.sm),
              _EndpointTile(
                label: 'To',
                icon: Icons.flag_rounded,
                station: _destination,
                onTap: () => _pick(false),
              ),
              const SizedBox(height: AppSpacing.xl),
              _PreferenceSelector(
                preference: _preference,
                wheelchairRequested: _wheelchairRequested,
                onPreferenceChanged: (value) {
                  setState(() => _preference = value);
                  _planJourney();
                },
                onWheelchairToggled: (value) => setState(() => _wheelchairRequested = value),
              ),
              const SizedBox(height: AppSpacing.xl),
              if (_loading)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpacing.xxl),
                  child: Center(child: CircularProgressIndicator()),
                ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.lg),
                  child: GlassSurface(
                    color: AppColors.danger.withValues(alpha: 0.12),
                    child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  ),
                ),
              if (_plan != null) ...[
                DelayedReveal(child: _PlanSummary(plan: _plan!, onPin: _pinJourney)),
                const SizedBox(height: AppSpacing.lg),
                DelayedReveal(
                  delay: const Duration(milliseconds: 80),
                  child: _RouteVisualization(plan: _plan!),
                ),
                const SizedBox(height: AppSpacing.lg),
                for (var i = 0; i < _plan!.legs.length; i++)
                  DelayedReveal(
                    delay: Duration(milliseconds: 120 + 60 * i),
                    child: Padding(
                      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                      child: _LegTile(leg: _plan!.legs[i]),
                    ),
                  ),
                const SizedBox(height: AppSpacing.lg),
                PrimaryButton(
                  label: 'Start journey mode',
                  icon: Icons.navigation_rounded,
                  expand: true,
                  onPressed: _startJourney,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _pick(bool isOrigin) async {
    final station = await showModalBottomSheet<Station>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      backgroundColor: Theme.of(context).colorScheme.surface,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.xl))),
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
  const _EndpointTile({required this.label, required this.icon, required this.station, required this.onTap});

  final String label;
  final IconData icon;
  final Station? station;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return GlassSurface(
      onTap: onTap,
      child: Row(
        children: [
          IconBadge(icon: icon, gradient: AppColors.heroGradientFor()),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(label.toUpperCase(), style: theme.textTheme.labelSmall),
                Text(station?.name ?? 'Choose $label station', style: theme.textTheme.titleLarge),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded),
        ],
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
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            for (final (value, label) in const [
              (RoutePreference.fastest, 'Fastest'),
              (RoutePreference.fewerTransfers, 'Fewer interchanges'),
              (RoutePreference.lessWalking, 'Less walking'),
            ])
              ChoiceChip(
                label: Text(label),
                selected: preference == value,
                showCheckmark: false,
                onSelected: (_) => onPreferenceChanged(value),
              ),
            FilterChip(
              label: const Text('Wheelchair-friendly'),
              selected: wheelchairRequested,
              showCheckmark: false,
              onSelected: onWheelchairToggled,
            ),
          ],
        ),
        if (wheelchairRequested)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Text(
              "Wheelchair-accessible routing isn't available for this network yet — showing the standard "
              'route instead.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.error),
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
    final theme = Theme.of(context);
    return GlassSurface(
      gradient: LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [AppColors.brandBlue.withValues(alpha: 0.94), AppColors.brandViolet.withValues(alpha: 0.94)],
      ),
      border: false,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('TRAVEL TIME',
                    style: theme.textTheme.labelSmall?.copyWith(color: Colors.white70)),
                Text(minutesLabel(plan.expectedTravelSeconds),
                    style: theme.textTheme.displaySmall?.copyWith(color: Colors.white)),
                const SizedBox(height: AppSpacing.lg),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    _MiniStat(label: 'Arrive', value: clockTime(plan.expectedArrivalAt)),
                    _MiniStat(label: 'Fare (est.)', value: '₹${fare.rupees}'),
                    _MiniStat(label: 'Interchanges', value: '${plan.interchangeCount}'),
                    _MiniStat(label: 'Walking', value: distanceLabel(plan.walkingDistanceM)),
                  ],
                ),
              ],
            ),
          ),
          IconPillButton(icon: Icons.push_pin_rounded, tooltip: 'Pin this journey', onPressed: onPin),
        ],
      ),
    );
  }
}

class _MiniStat extends StatelessWidget {
  const _MiniStat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.16), borderRadius: AppRadius.mdR),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 160),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(label.toUpperCase(),
                style: const TextStyle(
                    color: Colors.white70, fontSize: 9, fontWeight: FontWeight.w800, letterSpacing: 0.5)),
            Text(value,
                style: const TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.w800),
                maxLines: 2,
                overflow: TextOverflow.ellipsis),
          ],
        ),
      ),
    );
  }
}

/// The animated route visualisation: each ride leg "draws" itself in as a
/// bold coloured bar, walking transfers shown as a dotted connector.
class _RouteVisualization extends StatelessWidget {
  const _RouteVisualization({required this.plan});

  final JourneyPlan plan;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return GlassSurface(
      padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (var i = 0; i < plan.legs.length; i++)
            if (plan.legs[i].isRide)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  children: [
                    Container(
                      width: 10,
                      height: 10,
                      decoration: BoxDecoration(
                        color: routeColor(plan.legs[i].routeColor, plan.legs[i].routeLongName),
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Expanded(
                      child: DrawnBar(
                        key: ValueKey('${plan.origin.stopId}-${plan.destination.stopId}-leg-$i'),
                        color: routeColor(plan.legs[i].routeColor, plan.legs[i].routeLongName),
                        delay: Duration(milliseconds: 100 * i),
                      ),
                    ),
                    const SizedBox(width: AppSpacing.sm),
                    Text('${(plan.legs[i].stations?.length ?? 1) - 1} stops', style: theme.textTheme.labelSmall),
                  ],
                ),
              )
            else
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Row(
                  children: [
                    Icon(Icons.more_vert_rounded, size: 16, color: theme.colorScheme.outline),
                    const SizedBox(width: AppSpacing.sm),
                    Text('Walk ${distanceLabel(plan.legs[i].distanceM)}',
                        style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline)),
                  ],
                ),
              ),
        ],
      ),
    );
  }
}

class _LegTile extends StatelessWidget {
  const _LegTile({required this.leg});

  final JourneyLeg leg;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (!leg.isRide) {
      return GlassSurface(
        child: Row(
          children: [
            const IconBadge(icon: Icons.directions_walk_rounded),
            const SizedBox(width: AppSpacing.lg),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Walk to ${leg.alight.name}', style: theme.textTheme.titleMedium),
                  Text('${distanceLabel(leg.distanceM)} · about ${minutesLabel(leg.seconds)} on foot',
                      style: theme.textTheme.bodyMedium),
                ],
              ),
            ),
          ],
        ),
      );
    }
    return GlassSurface(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          IconBadge(icon: Icons.directions_subway_filled, gradient: AppColors.heroGradientFor()),
          const SizedBox(width: AppSpacing.lg),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                LineChip(label: leg.routeLongName ?? leg.routeId ?? 'Line', colorHex: leg.routeColor),
                const SizedBox(height: AppSpacing.sm),
                Text(
                  '${leg.board.name} → ${leg.alight.name}'
                  '${leg.platformHint != null ? '  ·  ${leg.platformHint}' : ''}',
                  style: theme.textTheme.bodyMedium,
                ),
                Text('${(leg.stations?.length ?? 1) - 1} stops · ${minutesLabel(leg.seconds)}',
                    style: theme.textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
