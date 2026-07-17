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
import '../../core/widgets/coach_chip.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/journey_progress_track.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/moment_row.dart';
import '../../data/api_client.dart';
import '../../domain/companion_messages.dart';
import '../../domain/journey_progress.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/replay.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart';
import 'journey_mode_providers.dart';
import 'journey_share.dart';

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
/// itself sourced from a live WS-tracked vehicle when one is bound and
/// fresh, falling back to a GTFS-timetable simulation otherwise (see
/// `journey_mode_providers.dart`). No fake GPS is ever synthesised — the
/// progress track's animated dot glides between whatever real fractions the
/// snapshot provides, and the source is always labelled honestly.
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
    // The title must follow the actual state: "You're on your way" over an
    // empty "not on a journey" body contradicted itself. And no LiveIndicator
    // here — the body already carries the honest LIVE TRACKING / SCHEDULED
    // ESTIMATE source pill, so a second connectivity-only "LIVE" badge in the
    // app bar was both redundant and misleading (it reflects the socket, not
    // the data).
    final hasJourney = journeyAsync.valueOrNull != null;
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: Text(hasJourney ? context.t.journeyInProgress : 'Journey'),
      ),
      body: AmbientBackground(
        intensity: 1.1,
        child: SafeArea(
          child: journeyAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => _JourneyLoadError(
              isConnectivityIssue: error is DioException && isConnectivityError(error),
              onRetry: () => ref.invalidate(activeJourneyProvider),
            ),
            data: (journey) => journey == null ? const _NoJourney() : _JourneyView(journey: journey),
          ),
        ),
      ),
    );
  }
}

class _NoJourney extends StatelessWidget {
  const _NoJourney();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 96,
              height: 96,
              decoration: BoxDecoration(gradient: AppColors.heroGradientFor(), shape: BoxShape.circle),
              child: const Icon(Icons.route_rounded, size: 44, color: Colors.white),
            ),
            const SizedBox(height: AppSpacing.xxl),
            Text(context.t.journeyNoJourney, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: AppSpacing.xxl),
            PrimaryButton(
              label: context.t.journeyPlanCta,
              icon: Icons.alt_route_rounded,
              onPressed: () => context.go('/planner'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Shown when the active-journey lookup itself fails — most often because
/// the app was relaunched mid-tunnel, with no signal to ask the server
/// whether a journey is in progress. Unlike the previous static message,
/// this always gives the user something to actually do next.
class _JourneyLoadError extends StatelessWidget {
  const _JourneyLoadError({required this.isConnectivityIssue, required this.onRetry});

  final bool isConnectivityIssue;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              isConnectivityIssue ? Icons.cloud_off_rounded : Icons.error_outline_rounded,
              size: 44,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
            const SizedBox(height: AppSpacing.lg),
            Text(
              isConnectivityIssue
                  ? "You're offline right now, so we can't check for an active journey."
                  : "We couldn't load your journey.",
              style: Theme.of(context).textTheme.titleMedium,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.xl),
            PrimaryButton(label: context.t.retry, icon: Icons.refresh_rounded, onPressed: onRetry),
          ],
        ),
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
    final exitLandmark = exit?['matched_landmark'] as String?;

    final origin = stations[journey.originStopId]?.name ?? journey.originStopId;
    final destination = stations[journey.destinationStopId]?.name ?? journey.destinationStopId;

    // Moment 2, "I'm entering the station": before any station has been
    // passed, the honest, available facts are Coach / Platform-direction /
    // Expected crowd — not a progress bar that reads 0%, and not a "Security
    // gate" this app has no real data source for.
    final isEnteringStation = (snapshot?.justBoarded ?? false) && snapshot?.arrived != true;

    final message = buildCompanionMessage(
      arrived: snapshot?.arrived ?? false,
      arrivingSoon: snapshot?.arrivingSoon ?? false,
      exitName: exitName,
      approachingInterchange: snapshot?.approachingInterchange ?? false,
      interchangeStationName: snapshot?.interchangeStationName,
      // Suppressed while isEnteringStation is showing its own Coach/Platform
      // MomentRows below — otherwise the "Hop on Coach X" banner would just
      // repeat what's already on screen.
      justBoarded: !isEnteringStation && (snapshot?.justBoarded ?? false),
      recommendedCoach: journeyContext?.recommendedCoach,
      platformHint: journeyContext?.platformHint,
      nextStationName: snapshot?.nextStationName,
    );

    final theme = Theme.of(context);
    final lineColor = routeColor(journeyContext?.routeColor, journeyContext?.routeLongName);
    final currentName = snapshot?.currentStationName ?? origin;
    final nextName = snapshot?.arrived == true ? destination : (snapshot?.nextStationName ?? destination);
    final isLive = snapshot?.source == JourneyProgressSource.liveVehicle;
    final isReconnecting = snapshot?.isReconnecting ?? false;

    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(AppSpacing.lg, 100, AppSpacing.lg, AppSpacing.xxl),
          children: [
            AnimatedSwitcher(
              duration: MediaQuery.of(context).disableAnimations
                  ? Duration.zero
                  : const Duration(milliseconds: 350),
              transitionBuilder: (child, animation) => FadeTransition(
                opacity: animation,
                child: SlideTransition(
                  position: Tween(begin: const Offset(0, -0.15), end: Offset.zero).animate(animation),
                  child: child,
                ),
              ),
              child: message == null
                  ? const SizedBox.shrink(key: ValueKey('no-message'))
                  : _CompanionBanner(key: ValueKey(message.text), message: message),
            ),
            if (journeyContext?.routeLongName != null) ...[
              LineChip(label: cleanLineName(journeyContext!.routeLongName), colorHex: journeyContext.routeColor),
              const SizedBox(height: AppSpacing.lg),
            ],

            if (isEnteringStation)
              _EnteringStationView(originName: currentName, journeyContext: journeyContext)
            else ...[
              // -- Current -> Next: the two-line "where am I" moment, Apple
              // Maps turn-by-turn style. Big, bold, nothing competing for
              // attention.
              Text(context.t.journeyNowAt, style: theme.textTheme.labelMedium),
              Text(currentName, style: theme.textTheme.headlineLarge),
              Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
                child: Icon(Icons.arrow_downward_rounded, color: lineColor, size: 22),
              ),
              Text(snapshot?.arrived == true ? context.t.journeyArrivedLabel : context.t.journeyNextStation,
                  style: theme.textTheme.labelMedium),
              Text(nextName, style: theme.textTheme.headlineLarge?.copyWith(color: lineColor)),

              const SizedBox(height: AppSpacing.xxl),

              // -- Progress.
              JourneyProgressTrack(fraction: snapshot?.fractionComplete, color: lineColor),
              const SizedBox(height: AppSpacing.sm),
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
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: (isReconnecting
                                ? AppColors.warning
                                : (isLive ? AppColors.live : theme.colorScheme.outline))
                            .withValues(alpha: 0.15),
                        borderRadius: AppRadius.pillR,
                      ),
                      child: Text(
                        // Reconnecting overrides either source label: it's
                        // honest about the connection regardless of whether
                        // the last-known data came from a live vehicle or
                        // the timetable simulation.
                        isReconnecting
                            ? 'RECONNECTING…'
                            : (isLive ? 'LIVE TRACKING' : 'SCHEDULED ESTIMATE'),
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: isReconnecting
                              ? AppColors.warning
                              : (isLive ? AppColors.live : theme.colorScheme.outline),
                        ),
                      ),
                    ),
                ],
              ),

              const SizedBox(height: AppSpacing.xxl),

              // -- Coach / Exit / ETA: a minimal vertical info list, not a
              // stat grid.
              Builder(builder: (context) {
                final rows = <Widget>[
                  if (journeyContext?.recommendedCoach != null)
                    MomentRow(
                      leading: const IconBadge(icon: Icons.event_seat_rounded),
                      title: Text(context.t.journeyCoach, style: theme.textTheme.bodyLarge),
                      subtitle: journeyContext!.coachReasons.isEmpty
                          ? null
                          : Text(journeyContext.coachReasons.first,
                              style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                      trailing: CoachChip(coach: journeyContext.recommendedCoach! + 1, dense: true),
                    ),
                  if (exitName != null)
                    MomentRow(
                      leading: const IconBadge(icon: Icons.exit_to_app_rounded),
                      title: Text(context.t.journeyExit, style: theme.textTheme.bodyLarge),
                      subtitle: exitLandmark == null
                          ? null
                          : Text('Near $exitLandmark',
                              style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                      trailing: Text(exitName, style: theme.textTheme.titleMedium),
                    ),
                  MomentRow(
                    leading: const IconBadge(icon: Icons.timer_outlined),
                    title: Text(context.t.journeyTimeRemaining, style: theme.textTheme.bodyLarge),
                    trailing: Text(
                      snapshot?.etaToDestination == null
                          ? '–'
                          : minutesLabel(snapshot!.etaToDestination!.inSeconds.toDouble()),
                      style: theme.textTheme.headlineSmall?.copyWith(color: lineColor),
                    ),
                  ),
                  if (snapshot?.delaySeconds != null && snapshot!.delaySeconds! > 120)
                    MomentRow(
                      leading: IconBadge(
                        icon: Icons.warning_amber_rounded,
                        color: AppColors.warning.withValues(alpha: 0.16),
                        foreground: AppColors.warning,
                      ),
                      title: Text(context.t.journeyRunningLate, style: theme.textTheme.bodyLarge),
                      trailing: Text(
                        minutesLabel(snapshot.delaySeconds),
                        style: theme.textTheme.titleMedium?.copyWith(color: AppColors.warning),
                      ),
                    ),
                ];
                return MomentList(children: rows);
              }),
            ],

            const SizedBox(height: AppSpacing.xxl),
            Row(
              children: [
                Expanded(
                  child: GhostButton(
                    label: context.t.journeyAbandon,
                    expand: true,
                    onPressed: () => _confirmAbandon(context, ref),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: PrimaryButton(
                    label: context.t.journeyArrived,
                    expand: true,
                    onPressed: () => _end(context, ref, completed: true),
                  ),
                ),
              ],
            ),

            // Share-my-live-journey: only while a journey is active (this
            // whole view only renders then). The user's OWN GPS is broadcast
            // to link-holders — honest microcopy lives inside the control.
            const SizedBox(height: AppSpacing.md),
            JourneyShareButton(journeyId: journey.id),
          ],
        ),
      ),
    );
  }

  /// Ending a journey early is hard to undo (the server marks it abandoned
  /// and the timetable simulation is torn down), so this is the one action
  /// on this screen that gets a confirmation step — unlike "I made it",
  /// which is always the expected, low-risk outcome.
  Future<void> _confirmAbandon(BuildContext context, WidgetRef ref) async {
    final confirmed = await showAppBottomSheet<bool>(
      context,
      builder: (sheetContext) => Padding(
        padding: const EdgeInsets.fromLTRB(AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(context.t.journeyEndConfirmTitle, style: Theme.of(sheetContext).textTheme.titleLarge),
            const SizedBox(height: AppSpacing.sm),
            Text(context.t.journeyEndConfirmBody, style: Theme.of(sheetContext).textTheme.bodyMedium),
            const SizedBox(height: AppSpacing.xl),
            Row(
              children: [
                Expanded(
                  child: GhostButton(
                    label: context.t.actionCancel,
                    expand: true,
                    onPressed: () => Navigator.of(sheetContext).pop(false),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: PrimaryButton(
                    label: context.t.journeyAbandon,
                    expand: true,
                    onPressed: () => Navigator.of(sheetContext).pop(true),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
    if (confirmed == true && context.mounted) await _end(context, ref, completed: false);
  }

  Future<void> _end(BuildContext context, WidgetRef ref, {required bool completed}) async {
    // The journey must be marked completed on the backend *before* fetching
    // its replay — otherwise Commute Replay would still find the previous
    // trip, not this one.
    try {
      await ref.read(journeyRepositoryProvider).end(journey.id, completed: completed);
    } on DioException {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Couldn't reach the server — check your connection and try again.")),
        );
      }
      return;
    }
    await ref.read(localStoreProvider).clearJourneyContext();
    ref
      ..invalidate(activeJourneyProvider)
      ..invalidate(recentJourneysProvider);

    if (completed && context.mounted) {
      final alreadyPinned = ref.read(pinnedJourneysProvider).any(
            (row) =>
                row['origin_stop_id'] == journey.originStopId &&
                row['destination_stop_id'] == journey.destinationStopId,
          );
      final alreadyDismissed = ref.read(localStoreProvider).hasDismissedSavePrompt(
            originStopId: journey.originStopId,
            destinationStopId: journey.destinationStopId,
          );
      await _showArrivalSheet(context, ref, offerSave: !alreadyPinned && !alreadyDismissed);
    }
    if (context.mounted) context.go('/');
  }

  /// The moment right after arriving: today's journey replayed (time/money/
  /// CO2 saved, all clearly estimated — see ReplayRepository), and, unless
  /// this route is already pinned, one tap to save it. Shows nothing at all
  /// if there's neither a replay nor a save prompt worth offering.
  Future<void> _showArrivalSheet(BuildContext context, WidgetRef ref, {required bool offerSave}) async {
    final replay = await ref.read(replayRepositoryProvider).latestTrip();
    if (!context.mounted) return;
    if (replay == null && !offerSave) return;

    final choice = await showAppBottomSheet<String>(
      context,
      builder: (sheetContext) => Padding(
        padding: const EdgeInsets.fromLTRB(AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("🎉 You're here!", style: Theme.of(sheetContext).textTheme.titleLarge),
            if (replay != null) ...[
              const SizedBox(height: AppSpacing.lg),
              _TripReplayCard(replay: replay),
            ],
            if (offerSave) ...[
              const SizedBox(height: AppSpacing.xl),
              Text('Save this journey?', style: Theme.of(sheetContext).textTheme.titleMedium),
              const SizedBox(height: AppSpacing.sm),
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  for (final label in const ['Home', 'Work'])
                    GhostButton(label: label, onPressed: () => Navigator.of(sheetContext).pop(label)),
                  GhostButton(label: 'Custom name…', onPressed: () => Navigator.of(sheetContext).pop('custom')),
                ],
              ),
            ],
            const SizedBox(height: AppSpacing.sm),
            Center(
              child: TextButton(
                onPressed: () {
                  if (offerSave) {
                    ref.read(localStoreProvider).dismissSavePrompt(
                          originStopId: journey.originStopId,
                          destinationStopId: journey.destinationStopId,
                        );
                  }
                  Navigator.of(sheetContext).pop();
                },
                child: Text(offerSave ? 'Not now' : 'Done'),
              ),
            ),
          ],
        ),
      ),
    );

    if (choice == null || !context.mounted) return;
    final label = choice == 'custom' ? await _promptCustomLabel(context) : choice;
    if (label == null || label.isEmpty) return;
    await ref.read(localStoreProvider).addPinnedJourney(
          originStopId: journey.originStopId,
          destinationStopId: journey.destinationStopId,
          label: label,
        );
  }

  Future<String?> _promptCustomLabel(BuildContext context) {
    final controller = TextEditingController();
    return showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Name this journey'),
        content: TextField(controller: controller, autofocus: true),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialogContext).pop(), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }
}

/// Moment 2, "I'm entering the station": Coach, Platform/direction, and
/// Expected crowd — the honest facts available before any station has been
/// passed. Deliberately has no "Security gate" row: DMRC publishes no data
/// distinguishing entry gates the way exits are distinguished, so this
/// omits it rather than inventing one.
class _EnteringStationView extends StatelessWidget {
  const _EnteringStationView({required this.originName, required this.journeyContext});

  final String originName;
  final JourneyContext? journeyContext;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final crowding = journeyContext?.crowding;
    final coachReasons = journeyContext?.coachReasons ?? const [];
    final crowdSourceLabel = switch (journeyContext?.crowdSource) {
      'observed' => 'Based on live crowd data',
      'prior' => 'Based on typical patterns',
      'model' => 'Estimated',
      _ => null,
    };
    final rows = <Widget>[
      if (journeyContext?.recommendedCoach != null)
        MomentRow(
          leading: const IconBadge(icon: Icons.event_seat_rounded),
          title: Text(context.t.journeyCoach, style: theme.textTheme.bodyLarge),
          subtitle: coachReasons.isEmpty
              ? null
              : Text(coachReasons.first,
                  style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
          trailing: CoachChip(coach: journeyContext!.recommendedCoach! + 1, dense: true),
        ),
      if (journeyContext?.platformHint != null)
        // The headsign ("Towards Noida Electronic City") is long free-form
        // text, so it lives in the full-width subtitle slot — as a trailing
        // widget it would squeeze the title down to a sliver and wrap it
        // character-by-character.
        MomentRow(
          leading: const IconBadge(icon: Icons.signpost_rounded),
          title: Text(context.t.platform, style: theme.textTheme.bodyLarge),
          subtitle: Text(journeyContext!.platformHint!, style: theme.textTheme.titleMedium),
        ),
      if (crowding != null && crowding != 'unknown')
        MomentRow(
          leading: const IconBadge(icon: Icons.groups_rounded),
          title: Text(context.t.crowding, style: theme.textTheme.bodyLarge),
          subtitle: crowdSourceLabel == null
              ? null
              : Text(crowdSourceLabel,
                  style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
          trailing: _CrowdPill(crowding: crowding),
        ),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('ENTERING THE STATION', style: theme.textTheme.labelMedium),
        Text(originName, style: theme.textTheme.headlineLarge),
        const SizedBox(height: AppSpacing.xxl),
        if (rows.isEmpty)
          Text("We'll have your coach and platform details shortly.", style: theme.textTheme.bodyMedium)
        else
          MomentList(children: rows),
      ],
    );
  }
}

class _CrowdPill extends StatelessWidget {
  const _CrowdPill({required this.crowding});

  final String crowding;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (crowding) {
      'low' => ('Quiet', AppColors.success),
      'moderate' => ('Moderate', AppColors.warning),
      _ => ('Crowded', AppColors.danger),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.xs),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.15), borderRadius: AppRadius.pillR),
      child: Text(label.toUpperCase(), style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color)),
    );
  }
}

class _CompanionBanner extends StatelessWidget {
  const _CompanionBanner({super.key, required this.message});

  final CompanionMessage message;

  @override
  Widget build(BuildContext context) {
    final (colors, icon) = switch (message.kind) {
      CompanionMessageKind.arrived => ([AppColors.success, AppColors.live], Icons.flag_circle_rounded),
      CompanionMessageKind.arriving => (AppColors.heroGradient, Icons.notifications_active_rounded),
      CompanionMessageKind.interchange => ([AppColors.brandViolet, AppColors.brandPink], Icons.transfer_within_a_station_rounded),
      CompanionMessageKind.boarding => (AppColors.heroGradient, Icons.directions_subway_filled),
      CompanionMessageKind.nextStation => ([AppColors.brandBlue, AppColors.brandBlue], Icons.arrow_forward_rounded),
    };
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.lg),
      child: GlassSurface(
        border: false,
        gradient: LinearGradient(colors: colors),
        child: Row(
          children: [
            Icon(icon, color: Colors.white),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Text(message.text,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w700, fontSize: 15)),
            ),
          ],
        ),
      ),
    );
  }
}

/// "Today's Journey" — the Commute Replay moment shown right after arriving.
/// Every figure is a documented estimate (see [ReplayRepository] /
/// commute_impact.py), so this deliberately omits a per-trip "walked Xm"
/// figure: exact walking distance for a historical trip isn't recorded
/// anywhere and would have to be invented to show it.
class _TripReplayCard extends StatelessWidget {
  const _TripReplayCard({required this.replay});

  final TripReplay replay;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final savedTime = replay.timeSavedSeconds > 0;
    final savedMoney = replay.moneySavedRupees > 0;
    final savedCarbon = replay.co2SavedKg > 0;

    final sentences = <String>[
      'You got from ${replay.originName} to ${replay.destinationName} in ${elapsedLabel(replay.durationSeconds)}.',
    ];
    if (savedTime && savedMoney) {
      sentences.add(
        'That saved about ${minutesLabel(replay.timeSavedSeconds)} and ₹${replay.moneySavedRupees} compared '
        'with a cab${savedCarbon ? ', and avoided about ${replay.co2SavedKg.toStringAsFixed(1)} kg of CO₂.' : '.'}',
      );
    } else if (savedMoney) {
      sentences.add('That saved about ₹${replay.moneySavedRupees} compared with a cab.');
    } else if (savedTime) {
      sentences.add('That saved about ${minutesLabel(replay.timeSavedSeconds)} compared with a cab.');
    } else if (savedCarbon) {
      sentences.add('You avoided about ${replay.co2SavedKg.toStringAsFixed(1)} kg of CO₂ compared with driving.');
    }

    return GlassSurface(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("TODAY'S JOURNEY", style: theme.textTheme.labelMedium),
          const SizedBox(height: AppSpacing.sm),
          Text(sentences.join(' '), style: theme.textTheme.bodyLarge),
        ],
      ),
    );
  }
}
