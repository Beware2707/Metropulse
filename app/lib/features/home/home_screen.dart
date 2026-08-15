import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../data/air_quality_service.dart';
import '../../core/l10n_ext.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/coach_chip.dart';
import '../../core/widgets/confidence_dots.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/live_indicator.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/reveal_animations.dart';
import '../../core/widgets/search_entry_pill.dart';
import '../../core/widgets/settle_fade_in.dart';
import '../../domain/commute_timeline.dart';
import '../../domain/fare.dart';
import '../../domain/home_context.dart';
import '../../domain/models/commute_card.dart';
import '../../domain/models/intelligence.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/station.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import 'home_providers.dart';

export 'home_providers.dart' show activeJourneyProvider, commuteCardProvider;

final _dayCaptionFormat = DateFormat('EEEE, h:mm a');

/// Home: Emotion → Decision → Action → Information. A greeting, one massive
/// search, then a single flowing list of whatever facts are actually true
/// right now — never a stack of bordered cards competing for attention.
class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  // The screen's data (commute timing, last train, alerts...) and the
  // "now" it's judged against are only ever fetched once per provider
  // build, so without a ticker the whole page freezes at whatever moment
  // it happened to load until something forces a rebuild -- pull-to-refresh
  // being the only such trigger otherwise. This keeps "leave in X min" and
  // similar honest without the user having to ask.
  Timer? _refreshTimer;

  @override
  void initState() {
    super.initState();
    _refreshTimer = Timer.periodic(const Duration(seconds: 30), (_) => _refresh());
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  void _refresh() {
    ref
      ..invalidate(commuteCardProvider)
      ..invalidate(activeJourneyProvider)
      ..invalidate(activeAlertsProvider)
      ..invalidate(recentJourneysProvider)
      ..invalidate(favouriteStationsProvider)
      ..invalidate(homeLastTrainProvider)
      ..invalidate(nearbyStationsProvider)
      ..invalidate(weatherProvider)
      ..invalidate(airQualityProvider);
  }

  @override
  Widget build(BuildContext context) {
    // Hide the "Plan a journey" FAB whenever a journey is already active —
    // its own banner is the action to take then, not a second route-planning
    // entry point competing for the same corner of the screen.
    final hasActiveJourney = ref.watch(activeJourneyProvider).valueOrNull != null;
    return Scaffold(
      extendBodyBehindAppBar: true,
      body: AmbientBackground(
        child: SafeArea(
          bottom: false,
          child: Stack(
            children: [
              RefreshIndicator(
                onRefresh: () async => _refresh(),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 640),
                    child: const _HomeContent(),
                  ),
                ),
              ),
              if (!hasActiveJourney)
                Positioned(
                  right: AppSpacing.lg,
                  bottom: 108,
                  child: SettleFadeIn(
                    child: PrimaryButton(
                      label: context.t.journeyPlanCta,
                      icon: Icons.alt_route_rounded,
                      onPressed: () => context.push('/planner'),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The opening moment: not a static "Good morning" but a day/time/weather
/// aware line, so the app already knows what day it is before being asked.
class _Header extends ConsumerWidget {
  const _Header();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final now = DateTime.now();
    final dayPart = dayPartFor(now);
    final card = ref.watch(commuteCardProvider).valueOrNull;
    final weather = ref.watch(weatherProvider).valueOrNull;
    final lastTrain = ref.watch(homeLastTrainProvider).valueOrNull;
    final lastTrainDeparture = DateTime.tryParse('${lastTrain?['departure_at']}');

    final message = resolveHomeContextMessage(
      now: now,
      leaveInSeconds: card?.leaveInSeconds?.round(),
      commuteDestinationName: card?.destinationName,
      lastTrainInSeconds: lastTrainDeparture?.difference(now).inSeconds,
    );

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_dayCaptionFormat.format(now), style: theme.textTheme.labelMedium),
              const SizedBox(height: 4),
              Row(
                children: [
                  Text(emojiForDayPart(dayPart), style: const TextStyle(fontSize: 18)),
                  const SizedBox(width: 8),
                  Flexible(child: Text(greetingForDayPart(dayPart), style: theme.textTheme.bodyLarge)),
                  if (weather != null) ...[
                    const SizedBox(width: 10),
                    Text(
                      '${weather.emoji} ${weather.roundedTemperatureC}°',
                      style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ],
                ],
              ),
              const SizedBox(height: 2),
              Text(message, style: theme.textTheme.titleLarge, maxLines: 2, overflow: TextOverflow.ellipsis),
            ],
          ),
        ),
        // Honest: the pill downgrades to SCHEDULE when the trains behind it
        // are schedule-interpolated rather than real GPS.
        LiveIndicator(
          dataEstimated:
              ref.watch(dataEstimatedProvider),
        ),
        const SizedBox(width: AppSpacing.sm),
        IconPillButton(
          icon: Icons.notifications_none_rounded,
          tooltip: 'Notifications',
          onPressed: () => context.push('/notifications'),
        ),
      ],
    );
  }
}

class _HomeContent extends ConsumerWidget {
  const _HomeContent();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final journey = ref.watch(activeJourneyProvider).valueOrNull;
    final isOffline = ref.watch(isOnlineProvider).valueOrNull == false;

    final raw = <Widget>[
      if (isOffline) ...[const _OfflineBanner(), const SizedBox(height: AppSpacing.lg)],
      const _Header(),
      const SizedBox(height: AppSpacing.xxxl),
      SearchEntryPill(hint: context.t.homeWhereTo, onTap: () => context.push('/search')),
      const SizedBox(height: AppSpacing.xxxl),
      if (journey != null) ...[const _ActiveJourneyBanner(), const SizedBox(height: AppSpacing.xl)],
      const _MomentsFlow(),
    ];

    return ListView(
      padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.sm, AppSpacing.lg, 180),
      children: [
        for (var i = 0; i < raw.length; i++) DelayedReveal(delay: Duration(milliseconds: 40 * i), child: raw[i]),
      ],
    );
  }
}

/// Honest, non-alarming context for why the screen might look sparser than
/// usual — Home otherwise swallows every failed fetch silently rather than
/// showing scary per-section errors, which is calm but can read as "there's
/// just nothing here" when the real reason is simply no connection.
class _OfflineBanner extends StatelessWidget {
  const _OfflineBanner();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return GlassSurface(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      child: Row(
        children: [
          Icon(Icons.cloud_off_rounded, size: 18, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              context.t.homeOfflineBanner,
              style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}

class _ActiveJourneyBanner extends StatelessWidget {
  const _ActiveJourneyBanner();

  @override
  Widget build(BuildContext context) {
    return GlassSurface(
      gradient: LinearGradient(colors: [AppColors.live.withValues(alpha: 0.92), AppColors.brandBlue.withValues(alpha: 0.92)]),
      border: false,
      onTap: () => context.go('/journey'),
      child: Row(
        children: [
          const Icon(Icons.navigation_rounded, color: Colors.white),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(context.t.journeyInProgress,
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 16)),
                Text(context.t.journeyReturnTap, style: const TextStyle(color: Colors.white70, fontSize: 13)),
              ],
            ),
          ),
          const Icon(Icons.chevron_right_rounded, color: Colors.white),
        ],
      ),
    );
  }
}

/// Everything that used to be a stack of separately-bordered card sections
/// (commute, alerts, favourites, nearby, last train, recent journeys) is now
/// one flowing, divider-separated list. A section that has nothing to say
/// right now contributes zero rows — it doesn't reserve empty space or show
/// an empty-state card of its own.
class _MomentsFlow extends ConsumerWidget {
  const _MomentsFlow();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.listen(serviceAlertBannerProvider, (_, __) => ref.invalidate(activeAlertsProvider));
    final rows = <Widget>[];

    final commute = ref.watch(commuteCardProvider);
    final prediction = ref.watch(commutePredictionProvider).valueOrNull;
    commute.when(
      loading: () {},
      error: (_, __) {},
      data: (card) {
        if (card != null) {
          rows.add(_CommuteRow(card: card));
        } else if (prediction != null) {
          rows.add(_SmartSuggestionRow(prediction: prediction));
        } else {
          rows.add(const _SetupCommuteRow());
        }
      },
    );

    final alerts = ref.watch(activeAlertsProvider).valueOrNull ?? const [];
    for (final alert in alerts) {
      rows.add(_AlertRow(alert: alert));
    }

    final pinned = ref.watch(pinnedJourneysProvider);
    final stations = ref.watch(stationIndexProvider);
    for (final journey in pinned) {
      rows.add(_PinnedJourneyRow(journey: journey, stations: stations));
    }

    final nearby = ref.watch(nearbyStationsProvider).valueOrNull;
    if (nearby is NearbyReady && nearby.stations.isNotEmpty) {
      final closest = nearby.stations.first;
      rows.add(
        MomentRow(
          leading: const IconBadge(icon: Icons.place_rounded),
          title: Text(closest.station.name, style: Theme.of(context).textTheme.titleMedium),
          subtitle: Text('${distanceLabel(closest.distanceM)} away', style: Theme.of(context).textTheme.bodyMedium),
          onTap: () => context.push('/station/${closest.station.stopId}'),
        ),
      );
    } else if (nearby is NearbyNeedsPermission) {
      rows.add(
        MomentRow(
          leading: const IconBadge(icon: Icons.location_off_rounded),
          title: Text(context.t.homeLocationOff, style: Theme.of(context).textTheme.titleMedium),
          trailing: GhostButton(
            label: context.t.homeEnableLocation,
            onPressed: () => ref.invalidate(nearbyStationsProvider),
          ),
        ),
      );
    }

    final favourites = ref.watch(favouriteStationsProvider).valueOrNull ?? const [];
    if (favourites.isNotEmpty) {
      final names = favourites.map((row) {
        final label = '${row['label'] ?? ''}'.trim();
        if (label.isNotEmpty) return label;
        return stations['${row['stop_id']}']?.name ?? '${row['stop_id']}';
      }).toList();
      rows.add(
        MomentRow(
          leading: const IconBadge(icon: Icons.star_rounded),
          title: Text(context.t.homeFavourites, style: Theme.of(context).textTheme.titleMedium),
          subtitle: Text(names.join(' · '), style: Theme.of(context).textTheme.bodyMedium),
          onTap: () => context.push('/favourites'),
        ),
      );
    }

    final airQuality = ref.watch(airQualityProvider).valueOrNull;
    if (airQuality != null) {
      rows.add(_AirQualityRow(air: airQuality));
    }

    final lastTrain = ref.watch(homeLastTrainProvider).valueOrNull;
    if (lastTrain != null) {
      rows.add(_LastTrainRow(info: lastTrain, stations: stations));
    }

    final recent = ref.watch(recentJourneysProvider).valueOrNull ?? const [];
    if (recent.isNotEmpty) {
      rows.add(_RecentJourneyRow(journey: recent.first, stations: stations, hasMore: recent.length > 1));
    }

    return MomentList(children: rows);
  }
}

// --- Commute / Smart suggestion / Setup ------------------------------------------

class _CommuteRow extends ConsumerWidget {
  const _CommuteRow({required this.card});

  final CommuteCard card;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final delay = ref.watch(commuteDelayEstimateProvider).valueOrNull;
    final status = card.leaveBy == null
        ? null
        : resolveCommuteTimelineStatus(
            now: DateTime.now(),
            leaveBy: card.leaveBy!,
            delaySeconds: delay?.expectedDelaySeconds ?? 0,
            routeLongName: card.routeLongName,
            delayConfidence: delay?.confidence,
          );
    final isUrgent = status != null && status.urgency != CommuteUrgency.onTime;

    // minutesLabel's sub-minute value is the bare word 'now', which cannot be
    // substituted into "Leave in {duration}" — it needs its own sentence.
    final leadLabel =
        card.leaveInSeconds != null ? minutesLabel(card.leaveInSeconds) : null;
    final leaveText = leadLabel == null
        ? context.t.homeNoDepartures
        : leadLabel == 'now'
            ? context.t.homeLeaveNow
            : context.t.homeLeaveIn(leadLabel);
    final routeText = '${card.originName} → ${card.destinationName}';

    return MomentRow(
      leading: IconBadge(
        icon: isUrgent ? Icons.warning_amber_rounded : Icons.directions_subway_filled_rounded,
        gradient: isUrgent ? null : AppColors.heroGradientFor(),
        color: isUrgent ? AppColors.warning.withValues(alpha: 0.16) : null,
        foreground: isUrgent ? AppColors.warning : null,
      ),
      title: Text(isUrgent ? status.headline : leaveText, style: theme.textTheme.titleLarge),
      subtitle: Text(
        status?.subline != null ? '${status!.subline} · $routeText' : routeText,
        style: theme.textTheme.bodyMedium,
      ),
      trailing: card.recommendedCoach != null ? CoachChip(coach: card.recommendedCoach! + 1, dense: true) : null,
      onTap: () => _showCommuteDetail(context, card),
    );
  }

  Future<void> _showCommuteDetail(BuildContext context, CommuteCard card) {
    return showAppBottomSheet(
      context,
      builder: (sheetContext) => Consumer(
        builder: (sheetContext, ref, __) {
          final theme = Theme.of(sheetContext);
          final suggestedPlan = ref.watch(homeSuggestedPlanProvider).valueOrNull;
          final fare = suggestedPlan == null ? null : estimateFare(suggestedPlan);
          final delay = ref.watch(commuteDelayEstimateProvider).valueOrNull;
          final coachReasons = ref.watch(homeCoachReasonsProvider).valueOrNull ?? const [];
          final status = card.leaveBy == null
              ? null
              : resolveCommuteTimelineStatus(
                  now: DateTime.now(),
                  leaveBy: card.leaveBy!,
                  delaySeconds: delay?.expectedDelaySeconds ?? 0,
                  routeLongName: card.routeLongName,
                  delayConfidence: delay?.confidence,
                );
          final steps = buildCommuteTimelineSteps(card: card, plan: suggestedPlan);
          final isUrgent = status != null && status.urgency != CommuteUrgency.onTime;

          return Padding(
            padding: const EdgeInsets.fromLTRB(AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xxl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(child: Text('TODAY', style: theme.textTheme.labelMedium)),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.outline.withValues(alpha: 0.15),
                        borderRadius: AppRadius.pillR,
                      ),
                      child: Text('SCHEDULE-BASED',
                          style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline)),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  status?.headline ?? card.greeting,
                  style: theme.textTheme.headlineSmall?.copyWith(color: isUrgent ? AppColors.warning : null),
                ),
                if (status?.subline != null) ...[
                  const SizedBox(height: 2),
                  Text(status!.subline!, style: theme.textTheme.bodyMedium),
                ],
                if (status?.reason != null) ...[
                  const SizedBox(height: AppSpacing.sm),
                  Row(
                    children: [
                      Icon(Icons.info_outline_rounded, size: 14, color: theme.colorScheme.onSurfaceVariant),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(status!.reason!,
                            style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                      ),
                      if (status.confidence != null) ...[
                        const SizedBox(width: AppSpacing.sm),
                        ConfidenceDots(confidence: status.confidence!),
                      ],
                    ],
                  ),
                ],
                if (card.routeLongName != null) ...[
                  const SizedBox(height: AppSpacing.md),
                  LineChip(
                    label: cleanLineName(card.routeLongName),
                    subtitle: routeDescription(card.routeLongName),
                    colorHex: card.routeColor,
                  ),
                ],
                const SizedBox(height: AppSpacing.lg),
                if (steps.isNotEmpty) ...[
                  _CommuteTimeline(steps: steps, coach: card.recommendedCoach, coachReasons: coachReasons),
                  const SizedBox(height: AppSpacing.lg),
                ],
                MomentList(
                  children: [
                    _DetailRow(label: context.t.crowding, value: card.crowding),
                    // The headsign ("Towards Noida Electronic City") is long
                    // free-form text: as a trailing widget it would squeeze
                    // the label into a sliver, so it takes the full-width
                    // subtitle slot instead.
                    if (card.platformHint != null)
                      MomentRow(
                        dense: true,
                        title: Text(context.t.platform, style: theme.textTheme.bodyMedium),
                        subtitle: Text(card.platformHint!, style: theme.textTheme.titleSmall),
                      ),
                    if (fare != null) _DetailRow(label: context.t.fareEstimate, value: '₹${fare.rupees}'),
                  ],
                ),
                const SizedBox(height: AppSpacing.lg),
                PrimaryButton(
                  label: context.t.homePlanThisRoute,
                  icon: Icons.alt_route_rounded,
                  expand: true,
                  onPressed: () {
                    Navigator.of(sheetContext).pop();
                    sheetContext.push('/planner');
                  },
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// The "Leave Home → Board → interchange(s) → Destination" timeline: a
/// timestamp column, a connecting dot-and-line rail, and each step's label —
/// interchange steps get a violet dot and a small "Change here" caption.
class _CommuteTimeline extends StatelessWidget {
  const _CommuteTimeline({required this.steps, this.coach, this.coachReasons = const []});

  final List<CommuteTimelineStep> steps;
  final int? coach;

  /// Why this coach, straight from the recommendation's own `reasons` list
  /// (e.g. "typically less crowded") — shown under the Board step, never
  /// invented when the list is empty.
  final List<String> coachReasons;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < steps.length; i++)
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 52,
                child: Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(clockTime(steps[i].time), style: theme.textTheme.labelMedium),
                ),
              ),
              const SizedBox(width: AppSpacing.md),
              Column(
                children: [
                  Container(
                    width: 10,
                    height: 10,
                    margin: const EdgeInsets.only(top: 6),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: steps[i].isInterchange ? AppColors.brandViolet : theme.colorScheme.primary,
                    ),
                  ),
                  if (i < steps.length - 1)
                    Expanded(
                      child: Container(
                        width: 2,
                        margin: const EdgeInsets.symmetric(vertical: 2),
                        color: theme.colorScheme.outlineVariant,
                      ),
                    ),
                ],
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.lg),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(steps[i].title, style: theme.textTheme.titleMedium),
                            if (steps[i].isInterchange)
                              Text('Change here',
                                  style: theme.textTheme.labelSmall?.copyWith(color: AppColors.brandViolet)),
                            if (i == 1 && coachReasons.isNotEmpty)
                              Text(
                                coachReasons.first,
                                style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                              ),
                          ],
                        ),
                      ),
                      if (i == 1 && coach != null) CoachChip(coach: coach! + 1, dense: true),
                    ],
                  ),
                ),
              ),
            ],
          ),
      ],
    );
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MomentRow(
      dense: true,
      title: Text(label, style: theme.textTheme.bodyMedium),
      trailing: Text(value, style: theme.textTheme.titleSmall),
    );
  }
}

class _SmartSuggestionRow extends StatelessWidget {
  const _SmartSuggestionRow({required this.prediction});

  final CommutePrediction prediction;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Metro Intelligence, quietly: a habit the app has noticed, not a model
    // confidence score — so the tiers read as "how well-worn is this
    // routine", never as ML jargon.
    final (confidenceLabel, confidenceColor) = switch (prediction.confidence) {
      >= 0.75 => ('Routine', AppColors.success),
      >= 0.4 => ('Noticed', AppColors.warning),
      _ => ('Hint', AppColors.brandBlue),
    };
    return MomentRow(
      leading: IconBadge(icon: Icons.insights_rounded, gradient: AppColors.heroGradientFor()),
      title: Text('${prediction.originName} → ${prediction.destinationName}', style: theme.textTheme.titleLarge),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text('Usually around ${clockTime(prediction.predictedDepartureAt)}', style: theme.textTheme.bodyMedium),
          Text(
            prediction.basis[0].toUpperCase() + prediction.basis.substring(1),
            style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
        ],
      ),
      trailing: Container(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.xs),
        decoration: BoxDecoration(color: confidenceColor.withValues(alpha: 0.15), borderRadius: AppRadius.pillR),
        child: Text(confidenceLabel.toUpperCase(), style: theme.textTheme.labelSmall?.copyWith(color: confidenceColor)),
      ),
      onTap: () => context.push('/planner?origin=${prediction.originStopId}&destination=${prediction.destinationStopId}'),
    );
  }
}

class _SetupCommuteRow extends StatelessWidget {
  const _SetupCommuteRow();

  @override
  Widget build(BuildContext context) {
    return MomentRow(
      leading: IconBadge(icon: Icons.add_home_work_rounded, gradient: AppColors.heroGradientFor()),
      title: Text(context.t.homeSetupCommuteTitle, style: Theme.of(context).textTheme.titleMedium),
      subtitle: Text(context.t.homeSetupCommuteBody, style: Theme.of(context).textTheme.bodyMedium),
      onTap: () => context.push('/favourites'),
    );
  }
}

// --- Alerts ---------------------------------------------------------------------

class _AlertRow extends StatelessWidget {
  const _AlertRow({required this.alert});

  final Map<String, dynamic> alert;

  @override
  Widget build(BuildContext context) {
    final severity = '${alert['severity']}';
    final row = MomentRow(
      leading: IconBadge(
        icon: switch (severity) {
          'severe' => Icons.error_rounded,
          'warning' => Icons.warning_rounded,
          _ => Icons.info_rounded,
        },
        color: switch (severity) {
          'severe' => AppColors.danger.withValues(alpha: 0.16),
          'warning' => AppColors.warning.withValues(alpha: 0.16),
          _ => null,
        },
        foreground: switch (severity) {
          'severe' => AppColors.danger,
          'warning' => AppColors.warning,
          _ => null,
        },
      ),
      title: Text('${alert['title']}', style: Theme.of(context).textTheme.titleMedium),
      subtitle: Text('${alert['description']}',
          maxLines: 2, overflow: TextOverflow.ellipsis, style: Theme.of(context).textTheme.bodyMedium),
    );
    if (severity != 'severe') return row;
    // A severe alert gets a faint whole-row tint too, not just its icon —
    // the one moment on Home that should read as unmissable even at a glance.
    return Container(
      decoration: BoxDecoration(color: AppColors.danger.withValues(alpha: 0.08), borderRadius: AppRadius.mdR),
      child: row,
    );
  }
}

// --- Pinned journeys --------------------------------------------------------------

class _PinnedJourneyRow extends StatelessWidget {
  const _PinnedJourneyRow({required this.journey, required this.stations});

  final Map<String, dynamic> journey;
  final Map<String, Station> stations;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final originName = stations['${journey['origin_stop_id']}']?.name ?? journey['origin_stop_id'];
    final destinationName = stations['${journey['destination_stop_id']}']?.name ?? journey['destination_stop_id'];
    final label = '${journey['label']}';
    final route = '$originName → $destinationName';
    return MomentRow(
      leading: const IconBadge(icon: Icons.push_pin_rounded),
      title: Text(label, style: theme.textTheme.titleMedium),
      // A label that's just the route typed back doesn't need repeating —
      // only show the route as a subtitle when it adds information the
      // title doesn't already carry.
      subtitle: label == route ? null : Text(route, style: theme.textTheme.bodyMedium),
      onTap: () => context.push(
        '/planner?origin=${journey['origin_stop_id']}&destination=${journey['destination_stop_id']}',
      ),
    );
  }
}

// --- Air quality ----------------------------------------------------------------

/// Current US AQI + PM2.5 with a severity colour and a one-line honest read,
/// plus — only when there's a usual commute route and published station
/// elevation data — how much of that route runs underground (where platform
/// air is a separate thing from the street AQI above). Degrades gracefully:
/// this row is only built when AQI is available, and the underground line
/// simply doesn't appear when there's no route or no data to back it.
class _AirQualityRow extends ConsumerWidget {
  const _AirQualityRow({required this.air});

  final AirQuality air;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final severity = aqiSeverity(air.usAqi);
    final undergroundShare = ref.watch(commuteUndergroundShareProvider).valueOrNull;

    return MomentRow(
      leading: IconBadge(
        icon: Icons.air_rounded,
        color: severity.color.withValues(alpha: 0.16),
        foreground: severity.color,
      ),
      title: Text('Air quality · US AQI ${air.usAqi}', style: theme.textTheme.titleMedium),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            '${severity.label} · PM2.5 ${air.pm25.round()}',
            style: theme.textTheme.bodyMedium?.copyWith(color: severity.color),
          ),
          if (undergroundShare != null)
            Text(
              'About $undergroundShare% of your usual route runs underground.',
              style: theme.textTheme.bodyMedium,
            ),
          const SizedBox(height: 2),
          Text(
            'Air quality: Open-Meteo · route mix from station data',
            style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline),
          ),
        ],
      ),
    );
  }
}

// --- Last train -----------------------------------------------------------------

class _LastTrainRow extends ConsumerWidget {
  const _LastTrainRow({required this.info, required this.stations});

  final Map<String, dynamic> info;
  final Map<String, Station> stations;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final departure = DateTime.tryParse('${info['departure_at']}');
    final stationName = stations['${info['stop_id']}']?.name ?? '${info['stop_id']}';
    return MomentRow(
      leading: const IconBadge(icon: Icons.nightlight_rounded),
      title: Text('$stationName · ${clockTime(departure)}', style: theme.textTheme.titleMedium),
      subtitle: Text('${info['headsign'] ?? info['route_id']}', style: theme.textTheme.bodyMedium),
      trailing: GhostButton(
        label: context.t.homeRemindMe,
        onPressed: () async {
          final messenger = ScaffoldMessenger.of(context);
          try {
            await ref.read(remindersRepositoryProvider).createLastTrain(
                  stopId: '${info['stop_id']}',
                  routeId: info['route_id'] as String?,
                );
            messenger.showSnackBar(const SnackBar(content: Text("You'll be reminded before it departs.")));
          } on DioException {
            messenger.showSnackBar(
              const SnackBar(content: Text("Couldn't reach the server — check your connection and try again.")),
            );
          }
        },
      ),
    );
  }
}

// --- Recent journeys --------------------------------------------------------------

class _RecentJourneyRow extends StatelessWidget {
  const _RecentJourneyRow({required this.journey, required this.stations, required this.hasMore});

  final Journey journey;
  final Map<String, Station> stations;
  final bool hasMore;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MomentRow(
      leading: IconBadge(
        icon: switch (journey.status) {
          'completed' => Icons.check_circle_rounded,
          'missed' => Icons.error_rounded,
          _ => Icons.remove_circle_rounded,
        },
        color: switch (journey.status) {
          'completed' => AppColors.success.withValues(alpha: 0.16),
          'missed' => AppColors.danger.withValues(alpha: 0.16),
          _ => null,
        },
        foreground: switch (journey.status) {
          'completed' => AppColors.success,
          'missed' => AppColors.danger,
          _ => null,
        },
      ),
      title: Text(
        '${stations[journey.originStopId]?.name ?? journey.originStopId}'
        ' → '
        '${stations[journey.destinationStopId]?.name ?? journey.destinationStopId}',
        style: theme.textTheme.titleMedium,
      ),
      subtitle: Text(hasMore ? '${journey.status} · see all recent journeys' : journey.status,
          style: theme.textTheme.bodyMedium),
      onTap: () => context.push('/journeys/history'),
    );
  }
}
