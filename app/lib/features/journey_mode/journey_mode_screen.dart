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
import '../../core/widgets/coach_chip.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/journey_progress_track.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/live_indicator.dart';
import '../../domain/companion_messages.dart';
import '../../domain/journey_progress.dart';
import '../../domain/models/journey.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart';
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
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text("You're on your way"),
        actions: const [Padding(padding: EdgeInsets.only(right: 16), child: Center(child: LiveIndicator()))],
      ),
      body: AmbientBackground(
        intensity: 1.1,
        child: SafeArea(
          child: journeyAsync.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (error, _) => const Center(child: Text("We couldn't load your journey. Please try again.")),
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

    final origin = stations[journey.originStopId]?.name ?? journey.originStopId;
    final destination = stations[journey.destinationStopId]?.name ?? journey.destinationStopId;

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
    final lineColor = routeColor(journeyContext?.routeColor, journeyContext?.routeLongName);
    final currentName = snapshot?.currentStationName ?? origin;
    final nextName = snapshot?.arrived == true ? destination : (snapshot?.nextStationName ?? destination);
    final isLive = snapshot?.source == JourneyProgressSource.liveVehicle;

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
              LineChip(label: journeyContext!.routeLongName!, colorHex: journeyContext.routeColor),
              const SizedBox(height: AppSpacing.lg),
            ],

            // -- Current -> Next: the two-line "where am I" moment, Apple
            // Maps turn-by-turn style. Big, bold, nothing competing for
            // attention.
            Text('NOW AT', style: theme.textTheme.labelMedium),
            Text(currentName, style: theme.textTheme.headlineLarge),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
              child: Icon(Icons.arrow_downward_rounded, color: lineColor, size: 22),
            ),
            Text(snapshot?.arrived == true ? 'ARRIVED' : 'NEXT STATION', style: theme.textTheme.labelMedium),
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
                      color: (isLive ? AppColors.live : theme.colorScheme.outline).withValues(alpha: 0.15),
                      borderRadius: AppRadius.pillR,
                    ),
                    child: Text(
                      isLive ? 'LIVE TRACKING' : 'ESTIMATED FROM TIMETABLE',
                      style: theme.textTheme.labelSmall
                          ?.copyWith(color: isLive ? AppColors.live : theme.colorScheme.outline),
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
                  _InfoRow(
                    icon: Icons.event_seat_rounded,
                    label: context.t.journeyCoach,
                    trailing: CoachChip(coach: journeyContext!.recommendedCoach! + 1, dense: true),
                  ),
                if (exitName != null)
                  _InfoRow(icon: Icons.exit_to_app_rounded, label: context.t.journeyExit, value: exitName),
                _InfoRow(
                  icon: Icons.timer_outlined,
                  label: context.t.journeyTimeRemaining,
                  value: snapshot?.etaToDestination == null
                      ? '–'
                      : minutesLabel(snapshot!.etaToDestination!.inSeconds.toDouble()),
                  valueStyle: theme.textTheme.headlineSmall?.copyWith(color: lineColor),
                ),
                if (snapshot?.delaySeconds != null && snapshot!.delaySeconds! > 120)
                  _InfoRow(
                    icon: Icons.warning_amber_rounded,
                    label: context.t.journeyRunningLate,
                    value: minutesLabel(snapshot.delaySeconds),
                    iconColor: AppColors.warning,
                  ),
              ];
              return GlassSurface(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl, vertical: AppSpacing.sm),
                child: Column(
                  children: [
                    for (var i = 0; i < rows.length; i++) ...[
                      if (i > 0) Divider(height: 1, color: theme.colorScheme.outlineVariant),
                      rows[i],
                    ],
                  ],
                ),
              );
            }),

            const SizedBox(height: AppSpacing.xxl),
            Row(
              children: [
                Expanded(
                  child: GhostButton(
                    label: context.t.journeyAbandon,
                    expand: true,
                    onPressed: () => _end(context, ref, completed: false),
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
          ],
        ),
      ),
    );
  }

  Future<void> _end(BuildContext context, WidgetRef ref, {required bool completed}) async {
    await ref.read(journeyRepositoryProvider).end(journey.id, completed: completed);
    await ref.read(localStoreProvider).clearJourneyContext();
    ref
      ..invalidate(activeJourneyProvider)
      ..invalidate(recentJourneysProvider);
    if (context.mounted) context.go('/');
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

/// One line of the minimal Coach / Exit / ETA info list: an icon, a label,
/// and either a plain value or a custom trailing widget (a [CoachChip]).
class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    this.value,
    this.trailing,
    this.valueStyle,
    this.iconColor,
  });

  final IconData icon;
  final String label;
  final String? value;
  final Widget? trailing;
  final TextStyle? valueStyle;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.lg),
      child: Row(
        children: [
          Icon(icon, size: 20, color: iconColor ?? theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: AppSpacing.md),
          Expanded(child: Text(label, style: theme.textTheme.bodyLarge)),
          if (trailing != null)
            trailing!
          else if (value != null)
            Text(value!, style: valueStyle ?? theme.textTheme.titleLarge),
        ],
      ),
    );
  }
}
