import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/l10n_ext.dart';
import '../../core/theme.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/reveal_animations.dart';
import '../../core/widgets/section_header.dart';
import '../../data/api_client.dart';
import '../../data/repositories.dart';
import '../../domain/crowding.dart';
import '../../domain/fare.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/station.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart';
import '../settings/settings_providers.dart';
import '../shared/station_search_sheet.dart';
import 'latest_departure.dart';

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
        title: Text(context.t.journeyPlanCta),
      ),
      body: AmbientBackground(
        intensity: 0.6,
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(AppSpacing.lg, 100, AppSpacing.lg, 48),
            children: [
              _EndpointTile(
                label: context.t.plannerFrom,
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
                label: context.t.plannerTo,
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
                stepFreePreferred: ref.watch(stepFreePreferredProvider),
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
                onStepFreeToggled: _onStepFreeToggled,
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
                if (ref.watch(stepFreePreferredProvider)) ...[
                  const SizedBox(height: AppSpacing.lg),
                  DelayedReveal(
                    delay: const Duration(milliseconds: 100),
                    child: _StepFreeInterchanges(plan: _plan!),
                  ),
                ],
                DelayedReveal(
                  delay: const Duration(milliseconds: 110),
                  child: _CrowdAdvisory(plan: _plan!),
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
                LatestDepartureRow(
                  origin: _origin!.stopId,
                  destination: _destination!.stopId,
                ),
                _OnwardSection(destination: _destination!),
                _MultimodalSection(origin: _origin!, destination: _destination!),
                const SizedBox(height: AppSpacing.lg),
                GhostButton(
                  label: context.t.plannerViewOnMap,
                  icon: Icons.account_tree_rounded,
                  expand: true,
                  onPressed: () => context.push(
                    '/network-map?origin=${_origin!.stopId}&destination=${_destination!.stopId}',
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                GhostButton(
                  label: context.t.plannerBuyTicket,
                  icon: Icons.confirmation_number_rounded,
                  expand: true,
                  onPressed: () => context.push('/tickets'),
                ),
                const SizedBox(height: AppSpacing.sm),
                GhostButton(
                  label: context.t.plannerParkAndRide,
                  icon: Icons.directions_car_rounded,
                  expand: true,
                  onPressed: () =>
                      context.push('/park-and-ride?destination=${_destination!.stopId}'),
                ),
                const SizedBox(height: AppSpacing.sm),
                PrimaryButton(
                  label: context.t.plannerLetsGo,
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
      builder: (_) => StationSearchSheet(
        title: isOrigin ? context.t.plannerWhereFrom : context.t.homeWhereTo,
        isOrigin: isOrigin,
      ),
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
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = isConnectivityError(error)
            ? context.t.plannerOfflineError
            : context.t.plannerNoRoute;
        _comparingPreferenceChange = false;
      });
    } on Exception {
      if (!mounted) return;
      setState(() {
        _error = context.t.plannerNoRoute;
        _comparingPreferenceChange = false;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// The "Step-free friendly" toggle nudges routing toward fewer changes —
  /// which is genuinely fewer stair/interchange transfers — and surfaces the
  /// interchange stations' facility facts under the plan. It makes no
  /// wheelchair-accessibility guarantee (see [stepFreeHonestyCaption]).
  Future<void> _onStepFreeToggled(bool value) async {
    final needsReplan =
        value && _preference != RoutePreference.fewerTransfers && !_loading;
    // Persist: the need follows the rider into Journey Mode and into their
    // next trip, instead of being re-stated on every plan.
    await ref.read(localStoreProvider).setStepFreePreferred(value);
    ref.invalidate(stepFreePreferredProvider);
    if (!mounted) return;
    setState(() {
      if (needsReplan) {
        _previousPlan = _plan;
        _previousPlanPreference = _preference;
        _comparingPreferenceChange = true;
        _preference = RoutePreference.fewerTransfers;
      }
    });
    if (needsReplan && _origin != null && _destination != null) {
      _planJourney();
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
              Text(context.t.plannerSaveRoute, style: Theme.of(sheetContext).textTheme.titleLarge),
              const SizedBox(height: AppSpacing.lg),
              TextField(controller: controller, autofocus: true),
              const SizedBox(height: AppSpacing.xl),
              Row(
                children: [
                  Expanded(
                    child: GhostButton(
                      label: context.t.actionCancel,
                      expand: true,
                      onPressed: () => Navigator.of(sheetContext).pop(),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: PrimaryButton(
                      label: context.t.actionSave,
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
          .showSnackBar(SnackBar(content: Text(context.t.plannerSavedToFavourites)));
    }
  }

  Future<void> _startJourney() async {
    final plan = _plan!;
    final firstRide = plan.legs.where((leg) => leg.isRide).firstOrNull;
    final repository = ref.read(journeyRepositoryProvider);
    final Journey journey;
    try {
      journey = await repository.start(
        origin: plan.origin.stopId,
        destination: plan.destination.stopId,
        routeId: firstRide?.routeId,
        interchangeStopIds: plan.interchangeStopIds,
      );
    } on DioException {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Couldn't reach the server — check your connection and try again.")),
        );
      }
      return;
    }

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

/// The destination station's curated last-mile (e-rickshaw) routes — the
/// same data the station detail screen shows, fetched through the existing
/// StationsRepository.lastMileRoutes.
final _onwardLastMileProvider = FutureProvider.autoDispose
    .family<List<Map<String, dynamic>>, String>((ref, stopId) {
  return ref.watch(stationsRepositoryProvider).lastMileRoutes(stopId);
});

/// Door-to-door options via the licensed Delhi Transport Stack planner,
/// keyed by the endpoint coordinates so a new plan refetches.
///
/// Kept alive deliberately. The DTS upstream takes ~20 s, and this section
/// sits low in a scrolling list, so its element unmounts the moment the user
/// scrolls past — with plain autoDispose that cancelled the in-flight request
/// and restarted it on the way back, so the section never resolved for anyone
/// who scrolled while waiting (observed on-device: three identical upstream
/// calls, nothing rendered). The result is cached for ten minutes; a new
/// origin/destination is a different key, so this never serves a stale route.
final _multimodalProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>?, String>((ref, key) {
  final link = ref.keepAlive();
  final timer = Timer(const Duration(minutes: 10), link.close);
  ref.onDispose(timer.cancel);
  final parts = key.split(',');
  return ref.watch(journeyRepositoryProvider).multimodalPlan(
        srcLat: double.parse(parts[0]),
        srcLon: double.parse(parts[1]),
        dstLat: double.parse(parts[2]),
        dstLon: double.parse(parts[3]),
      );
});

/// "Bus + metro, door to door": the top Transport Stack options between the
/// chosen stations. Hidden entirely when the server has no DTS key, on error,
/// or while loading — never a guessed route.
///
/// Honesty & license: every render carries the attribution string the
/// license requires, and DTS's own `response_type` is respected — "static"
/// options are labelled "timetable-based", and nothing here says "live"
/// unless DTS itself said so.
class _MultimodalSection extends ConsumerWidget {
  const _MultimodalSection({required this.origin, required this.destination});

  final Station origin;
  final Station destination;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final key =
        '${origin.lat},${origin.lon},${destination.lat},${destination.lon}';
    final async = ref.watch(_multimodalProvider(key));
    final theme = Theme.of(context);
    // The upstream is slow (~20 s). Say so, rather than leaving a silent gap
    // that reads as "there are no bus options".
    if (async.isLoading) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SectionHeader(title: 'Bus + metro, door to door'),
          Row(
            children: [
              const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              const SizedBox(width: AppSpacing.sm),
              Text('Checking bus routes…', style: theme.textTheme.bodySmall),
            ],
          ),
        ],
      );
    }
    final data = async.valueOrNull;
    final options = (data?['options'] as List? ?? const [])
        .whereType<Map<String, dynamic>>()
        .take(3)
        .toList();
    if (options.isEmpty) return const SizedBox.shrink();
    final allStatic =
        options.every((o) => '${o['response_type']}' == 'static');

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SectionHeader(title: 'Bus + metro, door to door'),
        MomentList(
          children: [
            for (final o in options)
              MomentRow(
                leading: const IconBadge(icon: Icons.directions_bus_rounded),
                title: Text(
                  '${(o['total_minutes'] as num?)?.round() ?? '–'} min · '
                  '${o['fare_unit'] ?? '₹'}${(o['total_fare'] as num?)?.round() ?? '–'}'
                  '${(o['reach_by'] ?? '') != '' ? ' · reach by ${_hhmm('${o['reach_by']}')}' : ''}',
                  style: theme.textTheme.titleMedium,
                ),
                subtitle: Text(
                  _legChain(o),
                  style: theme.textTheme.bodySmall,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
          ],
        ),
        Padding(
          padding: const EdgeInsets.only(top: AppSpacing.xs, left: AppSpacing.sm),
          child: Text(
            '${data!['attribution']}'
            '${allStatic ? ' · timetable-based' : ''}',
            style: theme.textTheme.labelSmall
                ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ),
      ],
    );
  }

  static String _hhmm(String hhmmss) =>
      hhmmss.length >= 5 ? hhmmss.substring(0, 5) : hhmmss;

  /// "walk 7 min → DTC 448 → Yellow Line" — the legs as a compact chain.
  static String _legChain(Map<String, dynamic> option) {
    final parts = <String>[];
    for (final l in (option['legs'] as List? ?? const [])) {
      if (l is! Map) continue;
      final kind = '${l['kind']}';
      switch (kind) {
        case 'walk':
          parts.add('walk ${(l['minutes'] as num?)?.round() ?? '?'} min');
        case 'bus':
          parts.add('${l['agency']} ${_busRoute('${l['route']}')}'.trim());
        case 'metro':
          parts.add('${_titleCase('${l['route']}')} Line');
        default:
          parts.add(kind);
      }
    }
    return parts.join(' → ');
  }

  /// '448DOWN' -> '448' (strip the direction suffix, an internal key).
  static String _busRoute(String raw) =>
      raw.replaceAll(RegExp(r'(UP|DOWN|STL.*)$', caseSensitive: true), '');

  static String _titleCase(String s) => s.isEmpty
      ? s
      : s[0].toUpperCase() + s.substring(1).toLowerCase();
}

@visibleForTesting
String multimodalLegChainForTest(Map<String, dynamic> option) =>
    _MultimodalSection._legChain(option);

/// Typical crowding along the planned route (origin + interchanges +
/// destination), keyed by the joined stop ids so a new plan refetches.
final _crowdForecastProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>?, String>((ref, stopsCsv) {
  return ref
      .watch(journeyRepositoryProvider)
      .crowdForecast(stopsCsv.split(','));
});

/// A one-line typical-crowding advisory for the planned route.
///
/// Wording discipline: everything here is an AVERAGE from a dated DMRC
/// snapshot, so the copy says "typically"/"usually" and never "now". A
/// quieter departure is only shown when the backend judged it meaningfully
/// quieter — the widget never does its own arithmetic on the ratios. When
/// no station on the route is busy, it renders nothing: quiet is the
/// default state of the world and doesn't need an announcement.
class _CrowdAdvisory extends ConsumerWidget {
  const _CrowdAdvisory({required this.plan});

  final JourneyPlan plan;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stops = <String>{
      plan.origin.stopId,
      ...plan.interchangeStopIds,
      plan.destination.stopId,
    }.join(',');
    final data = ref.watch(_crowdForecastProvider(stops)).valueOrNull;
    if (data == null) return const SizedBox.shrink();

    final busiest = data['busiest'] as Map<String, dynamic>?;
    if (busiest == null) return const SizedBox.shrink();
    final level = '${busiest['level']}';
    if (level != 'busy' && level != 'peak') return const SizedBox.shrink();

    final theme = Theme.of(context);
    final stations = ref.watch(stationIndexProvider);
    final busyName =
        stations['${busiest['stop_id']}']?.name ?? '${busiest['stop_id']}';

    final quieter = data['quieter'] as Map<String, dynamic>?;
    String? quieterLine;
    if (quieter != null) {
      final at = DateTime.tryParse('${quieter['depart_at']}')?.toLocal();
      final gain = ((quieter['gain'] as num?) ?? 0) * 100;
      if (at != null && gain > 0) {
        quieterLine =
            'Typically ~${gain.round()}% quieter leaving around ${clockTime(at)}.';
      }
    }

    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: GlassSurface(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.groups_rounded, size: 20, color: AppColors.warning),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    level == 'peak'
                        ? '$busyName is usually at its busiest around now'
                        : '$busyName is usually busy around now',
                    style: theme.textTheme.titleSmall,
                  ),
                  if (quieterLine != null) ...[
                    const SizedBox(height: 2),
                    Text(quieterLine, style: theme.textTheme.bodySmall),
                  ],
                  const SizedBox(height: 2),
                  Text(
                    'Typical for this hour · DMRC ridership data',
                    style: theme.textTheme.labelSmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// "Onward from {destination}": the door-to-door story — after the metro
/// legs, the real e-rickshaw continuations from the destination station.
/// Renders nothing while loading, on error, or when the station has no
/// curated last-mile routes.
class _OnwardSection extends ConsumerWidget {
  const _OnwardSection({required this.destination});

  final Station destination;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final routes =
        ref.watch(_onwardLastMileProvider(destination.stopId)).valueOrNull ??
            const <Map<String, dynamic>>[];
    if (routes.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(title: 'Onward from ${destination.name}'),
        MomentList(
          children: [
            for (final route in routes)
              MomentRow(
                leading: const IconBadge(icon: Icons.electric_rickshaw_rounded),
                title: Text(
                  '${route['route_long_name'] ?? route['route_short_name'] ?? 'Last-mile route'}',
                  style: theme.textTheme.titleMedium,
                ),
                subtitle: _OnwardSubtitle(route: route),
              ),
          ],
        ),
      ],
    );
  }
}

/// "every N min until HH:MM", then up to three destination stop names (the
/// route's `stops` array, minus the hub station itself at sequence 1).
class _OnwardSubtitle extends StatelessWidget {
  const _OnwardSubtitle({required this.route});

  final Map<String, dynamic> route;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    final headwaySecs = route['headway_secs'] as int?;
    final endTime = route['end_time'] as String?;
    final serviceParts = <String>[
      if (headwaySecs != null) 'every ${headwaySecs ~/ 60} min',
      if (endTime != null && endTime.length >= 5)
        'until ${endTime.substring(0, 5)}',
    ];

    final stops = (route['stops'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList();
    final destinations =
        stops.length > 1 ? stops.sublist(1) : const <Map<String, dynamic>>[];
    final names = destinations.take(3).map((s) => '${s['name']}').toList();
    final remaining = destinations.length - names.length;

    final lines = <Widget>[
      if (serviceParts.isNotEmpty)
        Text(serviceParts.join(' '), style: textTheme.bodySmall),
      if (names.isNotEmpty)
        Text(
          remaining > 0
              ? '${names.join(' - ')} +$remaining more'
              : names.join(' - '),
          style: textTheme.bodySmall,
        ),
    ];

    if (lines.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: lines);
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
                Text(station?.name ?? context.t.plannerChooseStation, style: theme.textTheme.titleLarge),
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
    required this.stepFreePreferred,
    required this.onPreferenceChanged,
    required this.onStepFreeToggled,
    this.deltaCaption,
  });

  final RoutePreference preference;
  final bool stepFreePreferred;
  final ValueChanged<RoutePreference> onPreferenceChanged;
  final ValueChanged<bool> onStepFreeToggled;
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
            for (final (value, label) in [
              (RoutePreference.fastest, context.t.plannerPrefFastest),
              (RoutePreference.fewerTransfers, context.t.plannerPrefFewerChanges),
              (RoutePreference.lessWalking, context.t.plannerPrefLessWalking),
            ])
              ChoiceChip(
                label: Text(label),
                selected: preference == value,
                showCheckmark: false,
                onSelected: (_) => onPreferenceChanged(value),
              ),
            FilterChip(
              avatar: const Icon(Icons.accessible_rounded, size: 18),
              label: Text(context.t.plannerStepFree),
              selected: stepFreePreferred,
              showCheckmark: false,
              onSelected: onStepFreeToggled,
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
      ],
    );
  }
}

/// The honest caveat shown with the step-free facility facts: we nudge toward
/// fewer changes and less walking (both real), but we have no live lift or
/// escalator status and make no wheelchair-accessibility guarantee.
const String stepFreeHonestyCaption =
    "We prefer routes with fewer changes and less walking. We don't yet have "
    'live lift or escalator status — check DMRC for step-free access on the day.';

/// Step-free access summary ({stop_id: elevated}) for the curated station
/// set, from the live facilities/summary endpoint. Empty while loading, on
/// 404, or offline — the card degrades to "not published" per station.
final _facilitiesSummaryProvider =
    FutureProvider.autoDispose<Map<String, bool?>>((ref) {
  return ref.watch(stationsRepositoryProvider).facilitiesSummary();
});

/// Under a step-free-preferred plan: the facility facts we actually have for
/// each interchange station (elevated vs underground), plus the honest
/// caveat. No fake "wheelchair accessible" guarantee — just the real facts.
class _StepFreeInterchanges extends ConsumerWidget {
  const _StepFreeInterchanges({required this.plan});

  final JourneyPlan plan;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final stations = ref.watch(stationIndexProvider);
    final elevated =
        ref.watch(_facilitiesSummaryProvider).valueOrNull ?? const {};
    final ids = plan.interchangeStopIds;

    return GlassSurface(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const IconBadge(icon: Icons.accessible_rounded),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(context.t.plannerStepFree, style: theme.textTheme.titleMedium),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          if (ids.isEmpty)
            Text(
              'This route has no interchanges — one train, no changes to make.',
              style: theme.textTheme.bodyMedium,
            )
          else
            for (final id in ids)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
                child: _InterchangeFact(
                  name: stations[id]?.name ?? id,
                  elevated: elevated[id],
                ),
              ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            stepFreeHonestyCaption,
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.outline),
          ),
        ],
      ),
    );
  }
}

/// One interchange station's real, published level fact: elevated,
/// underground, or "not published" when DMRC hasn't said (never guessed).
class _InterchangeFact extends StatelessWidget {
  const _InterchangeFact({required this.name, required this.elevated});

  final String name;
  final bool? elevated;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final (icon, fact) = switch (elevated) {
      true => (Icons.arrow_upward_rounded, 'Elevated station'),
      false => (Icons.arrow_downward_rounded, 'Underground station'),
      null => (Icons.help_outline_rounded, 'Level not published — check on the day'),
    };
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 18, color: theme.colorScheme.outline),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(name, style: theme.textTheme.titleSmall),
              Text(fact, style: theme.textTheme.bodySmall),
            ],
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
                Text(context.t.plannerTravelTime,
                    style: theme.textTheme.labelSmall?.copyWith(color: Colors.white70)),
                Text(minutesLabel(plan.expectedTravelSeconds),
                    style: theme.textTheme.displaySmall?.copyWith(color: Colors.white)),
                const SizedBox(height: AppSpacing.lg),
                Wrap(
                  spacing: 10,
                  runSpacing: 10,
                  children: [
                    _MiniStat(label: context.t.plannerStatArrive, value: clockTime(plan.expectedArrivalAt)),
                    _MiniStat(label: context.t.fareEstimate, value: '₹${fare.rupees}'),
                    _MiniStat(label: context.t.plannerStatChanges, value: '${plan.interchangeCount}'),
                    if (plan.walkingDistanceM > 0)
                      _MiniStat(label: context.t.plannerStatWalking, value: distanceLabel(plan.walkingDistanceM)),
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
                    Text(stopsLabel((plan.legs[i].stations?.length ?? 1) - 1), style: theme.textTheme.labelSmall),
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
                LineChip(label: cleanLineName(leg.routeLongName), colorHex: leg.routeColor),
                const SizedBox(height: AppSpacing.sm),
                Text('Board at ${leg.board.name}', style: theme.textTheme.titleMedium),
                Text(
                  '→ ${leg.alight.name}'
                  '${leg.platformHint != null ? '  ·  ${leg.platformHint}' : ''}',
                  style: theme.textTheme.bodyMedium,
                ),
                Text('${stopsLabel((leg.stations?.length ?? 1) - 1)} · ${minutesLabel(leg.seconds)}',
                    style: theme.textTheme.bodySmall),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
