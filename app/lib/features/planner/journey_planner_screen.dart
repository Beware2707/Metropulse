import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/reveal_animations.dart';
import '../../data/repositories.dart';
import '../../domain/crowding.dart';
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

  /// The plan in place right before the *current* re-plan was kicked off,
  /// paired with the preference it was computed under. Used to show a
  /// one-line "why" caption (e.g. "+4 min, 1 fewer change than Fastest")
  /// under the preference selector once the new plan lands — but only when
  /// a preference change (not a fresh origin/destination pick) triggered
  /// the re-plan.
  JourneyPlan? _previousPlan;
  RoutePreference? _previousPlanPreference;
  bool _comparingPreferenceChange = false;

  /// A short "why" caption comparing the current plan against the plan that
  /// was showing right before the route preference changed — e.g. "+4 min,
  /// 1 fewer change than Fastest". Null whenever there's nothing meaningful
  /// to compare (no previous plan, or the plan change wasn't caused by a
  /// preference switch).
  String? get _preferenceDeltaCaption {
    if (!_comparingPreferenceChange) return null;
    final previous = _previousPlan;
    final previousPreference = _previousPlanPreference;
    final current = _plan;
    if (previous == null || previousPreference == null || current == null) return null;

    final secondsDelta = current.expectedTravelSeconds - previous.expectedTravelSeconds;
    final changesDelta = current.interchangeCount - previous.interchangeCount;
    if (secondsDelta == 0 && changesDelta == 0) return null;

    final parts = <String>[];
    final minutesDelta = (secondsDelta / 60).round();
    if (minutesDelta != 0) {
      parts.add('${minutesDelta > 0 ? '+' : ''}$minutesDelta min');
    }
    if (changesDelta != 0) {
      final count = changesDelta.abs();
      final noun = count == 1 ? 'change' : 'changes';
      parts.add('${changesDelta < 0 ? '$count fewer' : '$count more'} $noun');
    }
    if (parts.isEmpty) return null;
    return '${parts.join(', ')} than ${_preferenceLabel(previousPreference)}';
  }

  String _preferenceLabel(RoutePreference preference) => switch (preference) {
        RoutePreference.fastest => 'Fastest',
        RoutePreference.fewerTransfers => 'Fewer changes',
        RoutePreference.lessWalking => 'Less walking',
      };

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
        title: const Text('Where are you going?'),
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
              Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
                child: Center(
                  child: IconPillButton(
                    icon: Icons.swap_vert_rounded,
                    tooltip: 'Swap origin and destination',
                    onPressed: _origin == null || _destination == null ? null : _swap,
                  ),
                ),
              ),
              _EndpointTile(
                label: 'To',
                icon: Icons.flag_rounded,
                station: _destination,
                onTap: () => _pick(false),
              ),
              if (_origin == null && _destination == null) ...[
                const SizedBox(height: AppSpacing.xl),
                _PinnedJourneysQuickPick(onPick: _pickPinned),
              ],
              const SizedBox(height: AppSpacing.xl),
              _PreferenceSelector(
                preference: _preference,
                wheelchairRequested: _wheelchairRequested,
                deltaCaption: _preferenceDeltaCaption,
                onPreferenceChanged: (value) {
                  if (_loading || value == _preference) return;
                  setState(() {
                    _previousPlan = _plan;
                    _previousPlanPreference = _preference;
                    _comparingPreferenceChange = true;
                    _preference = value;
                  });
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
                  label: "Let's go",
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

  /// Resolves a pinned journey's stop ids and plans it immediately — the
  /// same one-tap path Home's pinned-journey row and prediction chip use.
  Future<void> _pickPinned(String originStopId, String destinationStopId) async {
    final stations = ref.read(stationIndexProvider);
    setState(() {
      _origin = stations[originStopId];
      _destination = stations[destinationStopId];
      _plan = null;
      _error = null;
      _previousPlan = null;
      _previousPlanPreference = null;
      _comparingPreferenceChange = false;
    });
    if (_origin != null && _destination != null) await _planJourney();
  }

  Future<void> _pick(bool isOrigin) async {
    final station = await showAppBottomSheet<Station>(
      context,
      builder: (_) => StationSearchSheet(title: isOrigin ? 'Where from?' : 'Where to?', isOrigin: isOrigin),
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
      _previousPlan = null;
      _previousPlanPreference = null;
      _comparingPreferenceChange = false;
    });
    if (_origin != null && _destination != null) await _planJourney();
  }

  void _swap() {
    setState(() {
      final origin = _origin;
      _origin = _destination;
      _destination = origin;
      _plan = null;
      _previousPlan = null;
      _previousPlanPreference = null;
      _comparingPreferenceChange = false;
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
      setState(() {
        _error = "We couldn't find a route between these stations.";
        _comparingPreferenceChange = false;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pinJourney() async {
    final origin = _origin!;
    final destination = _destination!;
    final label = await showAppBottomSheet<String>(
      context,
      builder: (sheetContext) {
        final controller = TextEditingController(text: '${origin.name} → ${destination.name}');
        return Padding(
          padding: const EdgeInsets.fromLTRB(AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xxl),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Save this route', style: Theme.of(sheetContext).textTheme.titleLarge),
              const SizedBox(height: AppSpacing.lg),
              TextField(controller: controller, autofocus: true),
              const SizedBox(height: AppSpacing.xl),
              Row(
                children: [
                  Expanded(
                    child: GhostButton(
                      label: 'Cancel',
                      expand: true,
                      onPressed: () => Navigator.of(sheetContext).pop(),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: PrimaryButton(
                      label: 'Save',
                      expand: true,
                      onPressed: () => Navigator.of(sheetContext).pop(controller.text.trim()),
                    ),
                  ),
                ],
              ),
            ],
          ),
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
          .showSnackBar(const SnackBar(content: Text('Saved to your favourites!')));
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
      'crowding': expectedCrowding(coach?['coaches'] as List<dynamic>?),
      'coach_reasons': recommendedCoachReasons(coach),
      'crowd_source': crowdSource(coach),
    });

    ref
      ..invalidate(activeJourneyProvider)
      ..invalidate(recentJourneysProvider);
    if (mounted) context.go('/journey');
  }
}

/// A one-tap shortcut to a saved route, shown only while both endpoints are
/// still unset — a daily commuter with a pinned route shouldn't have to
/// pick both stations by hand every time.
class _PinnedJourneysQuickPick extends ConsumerWidget {
  const _PinnedJourneysQuickPick({required this.onPick});

  final void Function(String originStopId, String destinationStopId) onPick;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pinned = ref.watch(pinnedJourneysProvider);
    if (pinned.isEmpty) return const SizedBox.shrink();
    final stations = ref.watch(stationIndexProvider);
    final theme = Theme.of(context);
    return MomentList(
      children: [
        for (final journey in pinned)
          MomentRow(
            leading: const IconBadge(icon: Icons.push_pin_rounded),
            title: Text('${journey['label']}', style: theme.textTheme.titleMedium),
            subtitle: Text(
              '${stations['${journey['origin_stop_id']}']?.name ?? journey['origin_stop_id']}'
              ' → '
              '${stations['${journey['destination_stop_id']}']?.name ?? journey['destination_stop_id']}',
              style: theme.textTheme.bodyMedium,
            ),
            onTap: () => onPick('${journey['origin_stop_id']}', '${journey['destination_stop_id']}'),
          ),
      ],
    );
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
    this.deltaCaption,
  });

  final RoutePreference preference;
  final bool wheelchairRequested;
  final ValueChanged<RoutePreference> onPreferenceChanged;
  final ValueChanged<bool> onWheelchairToggled;
  final String? deltaCaption;

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
              (RoutePreference.fewerTransfers, 'Fewer changes'),
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
        if (deltaCaption != null)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Text(
              deltaCaption!,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.outline),
            ),
          ),
        if (wheelchairRequested)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.sm),
            child: Text(
              "We don't have wheelchair-accessible routing for this network yet — here's the standard "
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
                    _MiniStat(label: 'Changes', value: '${plan.interchangeCount}'),
                    if (plan.walkingDistanceM > 0)
                      _MiniStat(label: 'Walking', value: distanceLabel(plan.walkingDistanceM)),
                  ],
                ),
              ],
            ),
          ),
          IconPillButton(icon: Icons.push_pin_rounded, tooltip: 'Save this route', onPressed: onPin),
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
                Text('Board at ${leg.board.name}', style: theme.textTheme.titleMedium),
                Text(
                  '→ ${leg.alight.name}'
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
