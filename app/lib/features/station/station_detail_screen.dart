import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_motion.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/live_indicator.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/section_header.dart';
import '../../data/ws_client.dart';
import '../../domain/models/eta.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import '../favourites/favourites_screen.dart';
import '../notifications/notifications_providers.dart';
import 'last_train_reminder.dart';

final _lastTrainProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>?, String>((ref, stopId) async {
  return ref.watch(stationsRepositoryProvider).lastTrain(stopId);
});

final _exitsProvider = FutureProvider.autoDispose
    .family<List<Map<String, dynamic>>, String>((ref, stopId) async {
  return ref.watch(stationsRepositoryProvider).exits(stopId);
});

final _facilitiesProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>?, String>((ref, stopId) async {
  return ref.watch(stationsRepositoryProvider).facilities(stopId);
});

final _lastMileProvider = FutureProvider.autoDispose
    .family<List<Map<String, dynamic>>, String>((ref, stopId) async {
  return ref.watch(stationsRepositoryProvider).lastMileRoutes(stopId);
});

/// Per-train ETA for an arrivals-board row, keyed by vehicle id — the same
/// call `train_detail_screen.dart` and `live_map_screen.dart` make.
final _arrivalEtaProvider = FutureProvider.autoDispose.family<VehicleEta?, String>((ref, vehicleId) async {
  return ref.watch(trainsRepositoryProvider).eta(vehicleId);
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
    // Mirror the Live Map's honesty: when the trains feeding this board are
    // schedule-interpolated (or stale), the concrete ETAs below are NOT live
    // GPS, so add the same data-source caveat the map uses. The green
    // LiveIndicator only reflects WS connectivity, not data provenance.
    final arrivalsEstimated = ref.watch(arrivalsEstimatedProvider(stopId));
    final arrivalsStale = arrivals.any((t) => t.isStale);
    final lastTrain = ref.watch(_lastTrainProvider(stopId));
    final exits = ref.watch(_exitsProvider(stopId));
    final facilities = ref.watch(_facilitiesProvider(stopId));
    final lastMile = ref.watch(_lastMileProvider(stopId));

    // The last-train fact only feels urgent late at night; outside that
    // window it's demoted to a single low-key row near the bottom instead of
    // a prominent "Tonight" section.
    final hour = DateTime.now().hour;
    final isNight = hour >= 20 || hour < 4;

    final lastTrainRow = MomentRow(
      leading: const IconBadge(icon: Icons.nightlight_rounded, color: AppColors.night),
      title: Text('Last train', style: Theme.of(context).textTheme.titleMedium),
      subtitle: lastTrain.when(
        data: (data) => Text(
          data == null
              ? "We don't have tonight's service info yet"
              // Never fall back to route_id — it's an internal database key
              // ("2 at 12:42 AM" tells a commuter nothing). Show the headsign
              // when the feed has one, else just the time.
              : _lastTrainLabel(
                  data['headsign'] as String?,
                  DateTime.tryParse('${data['departure_at']}'),
                ),
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        loading: () => const Text('…'),
        error: (_, __) => const Text('Not available offline'),
      ),
    );

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: Text(station?.name ?? stopId),
        actions: [
          _FavouriteToggle(stopId: stopId),
          const SizedBox(width: AppSpacing.sm),
        ],
      ),
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(AppSpacing.lg, 100, AppSpacing.lg, AppSpacing.xxl),
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      'Arriving now',
                      style: Theme.of(context)
                          .textTheme
                          .headlineMedium
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                  ),
                  LiveIndicator(dataEstimated: arrivalsEstimated),
                ],
              ),
              if (arrivalsEstimated) ...[
                const SizedBox(height: AppSpacing.sm),
                GlassSurface(
                  blur: true,
                  borderRadius: AppRadius.pillR,
                  padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.schedule_rounded, size: 14, color: AppColors.warning),
                      const SizedBox(width: AppSpacing.xs),
                      Flexible(
                        child: Text(
                          'Arrival times are estimated from the schedule, not live GPS.',
                          style: Theme.of(context)
                              .textTheme
                              .labelSmall
                              ?.copyWith(color: AppColors.warning),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              if (arrivalsStale) ...[
                const SizedBox(height: AppSpacing.sm),
                Text(
                  'Positions may be a few minutes old.',
                  style: Theme.of(context)
                      .textTheme
                      .labelSmall
                      ?.copyWith(color: AppColors.danger),
                ),
              ],
              const SizedBox(height: AppSpacing.md),
              PrimaryButton(
                label: 'Plan a trip here',
                icon: Icons.alt_route_rounded,
                expand: true,
                onPressed: () => context.push('/planner?destination=$stopId'),
              ),
              const SizedBox(height: AppSpacing.lg),
              if (arrivals.isEmpty) const _EmptyArrivals(),
              for (final train in arrivals)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: GlassSurface(
                    onTap: () => context.push('/train/${train.id}'),
                    child: Row(
                      children: [
                        LineChip(label: train.lineLabel, colorHex: train.routeColor),
                        const SizedBox(width: AppSpacing.md),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(train.headsign == null ? train.lineLabel : 'Towards ${train.headsign}',
                                  style: Theme.of(context).textTheme.titleMedium),
                              train.atStation
                                  ? Text('At ${train.currentStation?.name}',
                                      style: Theme.of(context).textTheme.bodySmall)
                                  : _ArrivalEtaSubtitle(vehicleId: train.id),
                            ],
                          ),
                        ),
                        const Icon(Icons.chevron_right_rounded),
                      ],
                    ),
                  ),
                ),
              if (isNight) ...[
                const SectionHeader(title: 'Tonight'),
                GlassSurface(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      lastTrainRow,
                      _LastTrainReminderButton(stopId: stopId),
                    ],
                  ),
                ),
              ],
              const SectionHeader(title: 'Exits & nearby places'),
              exits.when(
                data: (data) => data.isEmpty
                    ? const EmptyState(icon: Icons.exit_to_app_rounded, message: "We don't have exit info for this station yet.")
                    : Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          MomentList(
                            children: [
                              for (final exit in data)
                                MomentRow(
                                  leading: const IconBadge(icon: Icons.exit_to_app_rounded),
                                  title: Text('${exit['name']}', style: Theme.of(context).textTheme.titleMedium),
                                  subtitle: _ExitLandmarks(exit: exit),
                                ),
                            ],
                          ),
                          if (data.any((e) => e['source'] == 'osm'))
                            Padding(
                              padding: const EdgeInsets.only(top: AppSpacing.xs, left: AppSpacing.sm),
                              child: Text(
                                'Gates & nearby places · © OpenStreetMap contributors',
                                style: Theme.of(context).textTheme.labelSmall?.copyWith(
                                    color: Theme.of(context).colorScheme.onSurfaceVariant),
                              ),
                            ),
                        ],
                      ),
                loading: () => const SizedBox.shrink(),
                error: (_, __) => const SizedBox.shrink(),
              ),
              facilities.when(
                data: (data) {
                  if (data == null) return const SizedBox.shrink();
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SectionHeader(title: 'Facilities'),
                      GlassSurface(child: _FacilitiesContent(data: data)),
                    ],
                  );
                },
                loading: () => const SizedBox.shrink(),
                error: (_, __) => const SizedBox.shrink(),
              ),
              if (lastMile.hasValue && lastMile.value!.isNotEmpty) ...[
                const SectionHeader(title: 'Last-mile options'),
                MomentList(
                  children: [
                    for (final route in lastMile.value!)
                      MomentRow(
                        leading: const IconBadge(icon: Icons.electric_rickshaw_rounded),
                        title: Text(
                          route['route_long_name'] ?? route['route_short_name'] ?? 'Last-mile route',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        subtitle: _LastMileSubtitle(route: route),
                      ),
                  ],
                ),
              ],
              if (!isNight && lastTrain.hasValue && lastTrain.value != null) ...[
                const SizedBox(height: AppSpacing.xxl),
                MomentList(children: [lastTrainRow]),
                _LastTrainReminderButton(stopId: stopId),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

/// The 'Facilities' section body: elevated/underground, toilet, gate
/// location, and parking lots, as curated rows — whichever facts the
/// backend has data for. The section itself is omitted entirely (see the
/// `facilities.when` call above) rather than shown empty, unlike Exits.
class _FacilitiesContent extends StatelessWidget {
  const _FacilitiesContent({required this.data});

  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final rows = <Widget>[];

    final elevated = data['elevated'] as bool?;
    if (elevated != null) {
      rows.add(MomentRow(
        leading: IconBadge(
          icon: elevated ? Icons.arrow_upward_rounded : Icons.arrow_downward_rounded,
        ),
        title: Text(
          elevated ? 'Elevated station' : 'Underground station',
          style: textTheme.titleMedium,
        ),
      ));
    }

    if (data['toilet'] == true) {
      rows.add(MomentRow(
        leading: const IconBadge(icon: Icons.wc_rounded),
        title: Text('Toilet available', style: textTheme.titleMedium),
      ));
    }

    final gateLocation = data['gate_location'] as String?;
    if (gateLocation != null && gateLocation.isNotEmpty) {
      rows.add(MomentRow(
        leading: const IconBadge(icon: Icons.signpost_rounded),
        title: Text(gateLocation, style: textTheme.titleMedium),
      ));
    }

    final parkingLots = data['parking_lots'] as List<dynamic>?;
    if (parkingLots != null && parkingLots.isNotEmpty) {
      for (final lot in parkingLots.whereType<Map<String, dynamic>>()) {
        final car = lot['car'] as int?;
        final cycle = lot['cycle'] as int?;
        final motorcycle = lot['motorcycle'] as int?;
        final parts = <String>[
          if (car != null) '$car cars',
          if (cycle != null) '$cycle bikes',
          if (motorcycle != null) '$motorcycle motorcycles',
        ];
        final operatorName = lot['operator'] as String?;
        rows.add(MomentRow(
          leading: const IconBadge(icon: Icons.local_parking_rounded),
          title: Text(parts.isEmpty ? 'Parking' : parts.join(' - '), style: textTheme.titleMedium),
          subtitle: operatorName != null && operatorName.isNotEmpty
              ? Text('Operated by $operatorName', style: textTheme.bodySmall)
              : null,
        ));
      }
    }

    return MomentList(children: rows);
  }
}

/// The 'Last-mile options' row subtitle: an operating-hours + headway
/// summary line, followed by a short list of destination stop names (the
/// route's `stops` array, excluding the hub stop itself at sequence 1).
class _LastMileSubtitle extends StatelessWidget {
  const _LastMileSubtitle({required this.route});

  final Map<String, dynamic> route;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    final startTime = route['start_time'] as String?;
    final endTime = route['end_time'] as String?;
    final headwaySecs = route['headway_secs'] as int?;
    // Flexible / demand-based e-rickshaw routes don't run a fixed timetable,
    // so soften "every N min" (which reads as a guaranteed cadence) to
    // "roughly every N min" for them. Match on the route name, case-insensitive.
    final routeName =
        '${route['route_long_name'] ?? route['route_short_name'] ?? ''}';
    final isFlexible = routeName.toLowerCase().contains('flexible');
    final hoursParts = <String>[
      if (startTime != null && endTime != null)
        'Runs ${startTime.substring(0, 5)}-${endTime.substring(0, 5)}'
      else if (startTime != null)
        'From ${startTime.substring(0, 5)}'
      else if (endTime != null)
        'Until ${endTime.substring(0, 5)}',
      if (headwaySecs != null)
        isFlexible
            ? 'roughly every ${headwaySecs ~/ 60} min'
            : 'every ${headwaySecs ~/ 60} min',
    ];

    final stops = (route['stops'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList();
    final destinations = stops.length > 1 ? stops.sublist(1) : const <Map<String, dynamic>>[];
    final destNames = destinations.take(4).map((s) => '${s['name']}').toList();
    final remaining = destinations.length - destNames.length;

    final lines = <Widget>[
      if (hoursParts.isNotEmpty) Text(hoursParts.join(' - '), style: textTheme.bodySmall),
      if (destNames.isNotEmpty)
        Text(
          remaining > 0 ? '${destNames.join(' - ')} +$remaining more' : destNames.join(' - '),
          style: textTheme.bodySmall,
        ),
    ];

    if (lines.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: lines);
  }
}

/// The landmarks near one exit gate. Prefers the structured `landmarks_detail`
/// (so tourist attractions can be flagged with an icon), falling back to the
/// flat `landmarks` string list for older/manually-curated exits.
class _ExitLandmarks extends StatelessWidget {
  const _ExitLandmarks({required this.exit});

  final Map<String, dynamic> exit;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final scheme = Theme.of(context).colorScheme;

    final detail = (exit['landmarks_detail'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList();

    if (detail.isEmpty) {
      // Fallback: flat landmarks string (no tourist flags available).
      final flat = exit['landmarks'];
      if (flat is List && flat.isNotEmpty) {
        return Text(flat.join(', '), style: textTheme.bodySmall);
      }
      return const SizedBox.shrink();
    }

    // Tourist places first (already sorted server-side, but be safe), capped.
    detail.sort((a, b) =>
        (b['tourist'] == true ? 1 : 0).compareTo(a['tourist'] == true ? 1 : 0));
    final shown = detail.take(6).toList();

    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Wrap(
        spacing: AppSpacing.sm,
        runSpacing: 4,
        children: [
          for (final l in shown)
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (l['tourist'] == true) ...[
                  Icon(Icons.attractions_rounded, size: 13, color: scheme.primary),
                  const SizedBox(width: 3),
                ],
                Text(
                  '${l['name']}',
                  style: textTheme.bodySmall?.copyWith(
                    color: l['tourist'] == true ? scheme.primary : null,
                    fontWeight: l['tourist'] == true ? FontWeight.w600 : null,
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

/// No live arrivals to show — but "no trains" reads as broken to a
/// first-time user if the WS connection simply hasn't finished (re)joining
/// yet, so this distinguishes "still connecting" from "genuinely nothing
/// scheduled".
class _EmptyArrivals extends ConsumerWidget {
  const _EmptyArrivals();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(wsStatusProvider).valueOrNull;
    final message = switch (status) {
      WsStatus.connecting => 'Connecting to live arrivals…',
      WsStatus.reconnecting => 'Reconnecting to live arrivals…',
      _ => 'No trains headed this way right now.',
    };
    return EmptyState(icon: Icons.train_rounded, message: message);
  }
}

/// Real per-row ETA for an approaching train, replacing the bare
/// "Approaching" label with an actual minutes-away figure once it resolves.
class _ArrivalEtaSubtitle extends ConsumerWidget {
  const _ArrivalEtaSubtitle({required this.vehicleId});

  final String vehicleId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final eta = ref.watch(_arrivalEtaProvider(vehicleId));
    final seconds = eta.valueOrNull?.nextStation?.etaSeconds;
    final label = seconds == null ? 'Approaching' : '${minutesLabel(seconds)} away';
    return Text(label, style: Theme.of(context).textTheme.bodySmall);
  }
}

/// "Remind me before the last train": posts the backend last-train reminder
/// (the reliable, cross-device path) AND schedules an on-device local
/// notification [lastTrainReminderLeadMinutes] before this station's last
/// boardable departure. Both are best-effort and fail honestly:
///  - unknown last-train time  -> a plain "can't set a reminder yet" note;
///  - last train under the lead -> "too soon" note, no false promise;
///  - notification permission denied / schedule refused -> the backend
///    reminder still stands, and the SnackBar says the device alert didn't.
class _LastTrainReminderButton extends ConsumerStatefulWidget {
  const _LastTrainReminderButton({required this.stopId});

  final String stopId;

  @override
  ConsumerState<_LastTrainReminderButton> createState() =>
      _LastTrainReminderButtonState();
}

class _LastTrainReminderButtonState
    extends ConsumerState<_LastTrainReminderButton> {
  bool _busy = false;
  bool _scheduled = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final data = ref.watch(_lastTrainProvider(widget.stopId)).valueOrNull;
    final departureAt = DateTime.tryParse('${data?['departure_at']}');

    Widget note(String text) => Padding(
          padding: const EdgeInsets.only(top: AppSpacing.sm),
          child: Text(
            text,
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.outline),
          ),
        );

    if (data == null || departureAt == null) {
      return note("We can't set a reminder until tonight's last-train time is known.");
    }

    if (_scheduled) {
      return note("Reminder set — we'll nudge you $lastTrainReminderLeadMinutes minutes before it leaves.");
    }

    final fireAt = lastTrainReminderTime(
      departureAt: departureAt,
      now: DateTime.now(),
    );
    if (fireAt == null) {
      return note('The last train is under $lastTrainReminderLeadMinutes minutes away — too soon to set a reminder.');
    }

    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.sm),
      child: GhostButton(
        label: 'Remind me before the last train',
        icon: Icons.notifications_active_rounded,
        expand: true,
        onPressed: _busy ? null : () => _schedule(data, departureAt, fireAt),
      ),
    );
  }

  Future<void> _schedule(
    Map<String, dynamic> data,
    DateTime departureAt,
    DateTime fireAt,
  ) async {
    setState(() => _busy = true);

    // The backend reminder is the dependable path (it survives an app
    // restart); a failure here shouldn't block the on-device attempt.
    try {
      await ref.read(remindersRepositoryProvider).createLastTrain(
            stopId: widget.stopId,
            routeId: data['route_id'] as String?,
            directionId: (data['direction_id'] as num?)?.toInt(),
            leadMinutes: lastTrainReminderLeadMinutes,
          );
    } on Exception {
      // Best-effort; the local notification below is still worth trying.
    }

    final stationName =
        ref.read(stationIndexProvider)[widget.stopId]?.name ?? widget.stopId;
    final scheduled = await ref.read(notificationsServiceProvider).scheduleAt(
          id: widget.stopId.hashCode & 0x7fffffff,
          title: 'Last train soon',
          body:
              'The last train from $stationName leaves at ${clockTime(departureAt)}. '
              'Time to head for the platform.',
          when: fireAt,
        );

    if (!mounted) return;
    setState(() {
      _busy = false;
      _scheduled = scheduled;
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          scheduled
              ? 'Reminder set for ${clockTime(fireAt)} — $lastTrainReminderLeadMinutes minutes before the last train.'
              : "We saved your reminder, but couldn't set a device alert — check notification permissions in Settings.",
        ),
      ),
    );
  }
}

/// The favourite-star toggle, kept optimistic: the icon flips the instant
/// you tap it, the save/remove call happens in the background, and only
/// then does the favourites provider get invalidated to reconcile with the
/// server. If the call throws, the optimistic flag reverts.
class _FavouriteToggle extends ConsumerStatefulWidget {
  const _FavouriteToggle({required this.stopId});

  final String stopId;

  @override
  ConsumerState<_FavouriteToggle> createState() => _FavouriteToggleState();
}

class _FavouriteToggleState extends ConsumerState<_FavouriteToggle> {
  bool? _optimistic;

  @override
  Widget build(BuildContext context) {
    final favourites = ref.watch(favouriteStationsProvider);
    final serverFavourite = favourites.valueOrNull?.any((f) => f['stop_id'] == widget.stopId) ?? false;
    final isFavourite = _optimistic ?? serverFavourite;

    final reduceMotion = MediaQuery.of(context).disableAnimations;

    return IconButton(
      icon: AnimatedSwitcher(
        duration: reduceMotion ? Duration.zero : AppMotion.fast,
        transitionBuilder: (child, animation) => ScaleTransition(scale: animation, child: child),
        child: Icon(
          isFavourite ? Icons.star_rounded : Icons.star_outline_rounded,
          key: ValueKey(isFavourite),
          color: isFavourite ? AppColors.warning : null,
        ),
      ),
      onPressed: () async {
        final next = !isFavourite;
        setState(() => _optimistic = next);
        final repository = ref.read(favouritesRepositoryProvider);
        try {
          if (next) {
            await repository.save(widget.stopId);
          } else {
            await repository.remove(widget.stopId);
          }
          ref.invalidate(favouriteStationsProvider);
        } catch (_) {
          if (mounted) setState(() => _optimistic = !next);
        }
      },
    );
  }
}

/// Builds the exit-landmarks subtitle for one exit map, for widget tests
/// (the widget itself is private to this screen).
@visibleForTesting
Widget exitLandmarksForTest(Map<String, dynamic> exit) => _ExitLandmarks(exit: exit);

/// The last-train line for a station. Uses the trip headsign when the feed has
/// one ("Towards Rithala at 11:42 PM"); otherwise just the time — never the
/// raw route_id, which is an internal key and meaningless to a commuter.
String _lastTrainLabel(String? headsign, DateTime? departureAt) {
  final time = clockTime(departureAt);
  final towards = (headsign != null && headsign.trim().isNotEmpty)
      ? _towardsPrefixed(headsign.trim())
      : null;
  return towards == null ? 'Last train at $time' : '$towards at $time';
}

String _towardsPrefixed(String headsign) =>
    headsign.toLowerCase().startsWith('towards') ? headsign : 'Towards $headsign';
