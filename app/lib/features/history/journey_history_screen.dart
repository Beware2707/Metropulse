import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_motion.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/section_header.dart';
import '../../core/widgets/shimmer_skeleton.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/station.dart';
import '../../providers/core_providers.dart';
import '../replay/fare_advisor_card.dart';

final _dateGroupFormat = DateFormat('EEEE, d MMMM');

/// Maps a journey's raw status string to calmer, human copy — the list
/// should read like a summary of your day, not a debug log.
String _statusLabel(String status) => switch (status) {
      'completed' => 'Arrived',
      'missed' => 'Missed train',
      'abandoned' => 'Cancelled',
      _ => 'In progress',
    };

/// "Today" / "Yesterday" / a weekday-and-date string for anything older —
/// used as client-side date-group headers over the already-sorted history.
String _dateGroupLabel(DateTime timestamp) {
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final day = timestamp.toLocal();
  final startOfDay = DateTime(day.year, day.month, day.day);
  final difference = today.difference(startOfDay).inDays;
  if (difference == 0) return 'Today';
  if (difference == 1) return 'Yesterday';
  return _dateGroupFormat.format(day);
}

bool _isSameDay(DateTime a, DateTime b) {
  final localA = a.toLocal();
  final localB = b.toLocal();
  return localA.year == localB.year && localA.month == localB.month && localA.day == localB.day;
}

/// The full journey history (as opposed to Home's short "recent" preview),
/// offline-cached so it remains browsable without connectivity.
final journeyHistoryFullProvider = FutureProvider<List<Journey>>(
  (ref) => ref.watch(journeyRepositoryProvider).history(limit: 100),
);

/// "This Month" — the rolling Commute Replay summary shown at the top of
/// journey history, similar in spirit to a music-streaming year-in-review,
/// but for commuting. Every figure is a documented estimate (see
/// ReplayRepository / commute_impact.py).
final monthlyReplayProvider = FutureProvider(
  (ref) => ref.watch(replayRepositoryProvider).monthly(),
);

class JourneyHistoryScreen extends ConsumerWidget {
  const JourneyHistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final journeys = ref.watch(journeyHistoryFullProvider);
    final stations = ref.watch(stationIndexProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Where you\'ve been')),
      body: AmbientBackground(
        intensity: 0.4,
        child: SafeArea(
          child: Column(
            children: [
              const _MonthlyReplayHeader(),
              const FareAdvisorCard(),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () async {
                    ref.invalidate(journeyHistoryFullProvider);
                    ref.invalidate(monthlyReplayProvider);
                  },
                  child: journeys.when(
              loading: () => ListView(
                padding: const EdgeInsets.all(AppSpacing.lg),
                children: const [
                  ShimmerBlock(height: 72),
                  SizedBox(height: AppSpacing.sm),
                  ShimmerBlock(height: 72),
                  SizedBox(height: AppSpacing.sm),
                  ShimmerBlock(height: 72),
                ],
              ),
              error: (error, _) => ListView(
                padding: const EdgeInsets.all(AppSpacing.lg),
                children: [
                  const SizedBox(height: 64),
                  EmptyState(
                    icon: Icons.cloud_off_rounded,
                    message: "We couldn't load your trips.",
                    actionLabel: 'Try again',
                    onAction: () => ref.invalidate(journeyHistoryFullProvider),
                  ),
                ],
              ),
              data: (data) => data.isEmpty
                  ? ListView(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      children: const [
                        SizedBox(height: 96),
                        EmptyState(icon: Icons.history_rounded, message: 'Your trips will show up here once you take one.'),
                      ],
                    )
                  : ListView(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      children: [
                        for (var index = 0; index < data.length; index++) ...[
                          if (index == 0 || !_isSameDay(data[index].startedAt, data[index - 1].startedAt))
                            SectionHeader(
                              title: _dateGroupLabel(data[index].startedAt),
                              padding: EdgeInsets.only(top: index == 0 ? 0 : AppSpacing.xl, bottom: AppSpacing.sm),
                            ),
                          if (index > 0 && _isSameDay(data[index].startedAt, data[index - 1].startedAt))
                            const MomentDivider(),
                          _JourneyRow(journey: data[index], stations: stations),
                        ],
                      ],
                    ),
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

/// A single past trip: purely informational (no `onTap`, no chevron) since
/// there's no per-journey detail route to navigate to.
class _JourneyRow extends StatelessWidget {
  const _JourneyRow({required this.journey, required this.stations});

  final Journey journey;
  final Map<String, Station> stations;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return MomentRow(
      leading: IconBadge(
        icon: switch (journey.status) {
          'completed' => Icons.check_circle_rounded,
          'missed' => Icons.error_rounded,
          'abandoned' => Icons.remove_circle_rounded,
          _ => Icons.pending_rounded,
        },
        color: switch (journey.status) {
          'missed' || 'abandoned' => AppColors.danger.withValues(alpha: 0.16),
          _ => null,
        },
        foreground: switch (journey.status) {
          'missed' || 'abandoned' => AppColors.danger,
          _ => null,
        },
      ),
      title: Text(
        '${stations[journey.originStopId]?.name ?? journey.originStopId}'
        ' → '
        '${stations[journey.destinationStopId]?.name ?? journey.destinationStopId}',
        style: theme.textTheme.titleMedium,
      ),
      subtitle: Text('${_statusLabel(journey.status)} · ${clockTime(journey.startedAt)}',
          style: theme.textTheme.bodySmall),
    );
  }
}

/// A rough, sentence-friendly duration ("42 minutes" / "3 hours") for the
/// monthly narrative — the same underlying seconds `minutesLabel` formats
/// elsewhere, just phrased for a sentence instead of a stat chip.
String _narrativeDuration(double seconds) {
  final minutes = (seconds / 60).round();
  if (minutes < 60) return '$minutes minutes';
  final hours = (minutes / 60).round();
  return hours == 1 ? '1 hour' : '$hours hours';
}

/// "This Month" at the top of history — a story, not a stat grid. Nothing
/// shown until there's at least one trip to report on: an all-zero card
/// would read as broken, not honest.
///
/// The card fades + slides in once the async `monthlyReplayProvider`
/// resolves, instead of popping in and shoving the trip list down with a
/// visible layout jump.
class _MonthlyReplayHeader extends ConsumerWidget {
  const _MonthlyReplayHeader();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final monthly = ref.watch(monthlyReplayProvider).valueOrNull;

    Widget card = const SizedBox.shrink(key: ValueKey('replay-empty'));

    if (monthly != null && monthly.tripCount > 0) {
      final theme = Theme.of(context);
      final tripWord = monthly.tripCount == 1 ? 'time' : 'times';
      final sentences = <String>['This month you chose the metro ${monthly.tripCount} $tripWord.'];

      final savedMoney = monthly.totalMoneySavedRupees > 0;
      final savedCarbon = monthly.totalCo2SavedKg > 0;
      final savedTime = monthly.totalTimeSavedSeconds > 0;
      if (savedMoney && savedCarbon) {
        sentences.add(
          'You saved about ₹${monthly.totalMoneySavedRupees} compared with ride-hailing, and avoided about '
          '${monthly.totalCo2SavedKg.toStringAsFixed(0)} kg of CO₂.',
        );
      } else if (savedMoney) {
        sentences.add('You saved about ₹${monthly.totalMoneySavedRupees} compared with ride-hailing.');
      } else if (savedCarbon) {
        sentences.add('You avoided about ${monthly.totalCo2SavedKg.toStringAsFixed(0)} kg of CO₂ compared with driving.');
      }
      if (savedTime) {
        sentences.add("That's also ${_narrativeDuration(monthly.totalTimeSavedSeconds)} you didn't spend stuck in traffic.");
      }

      card = GlassSurface(
        key: ValueKey('replay-content-${monthly.periodStart.toIso8601String()}'),
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('THIS MONTH', style: theme.textTheme.labelMedium),
            const SizedBox(height: AppSpacing.sm),
            Text(sentences.join(' '), style: theme.textTheme.headlineSmall),
            if (savedMoney || savedCarbon || savedTime) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                'Estimated by comparing your trip times and fares against typical cab prices and average '
                'car emissions for the same distance.',
                style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
              ),
            ],
          ],
        ),
      );
    }

    final reduceMotion = MediaQuery.of(context).disableAnimations;

    return Padding(
      padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 0),
      child: AnimatedSwitcher(
        duration: reduceMotion ? Duration.zero : AppMotion.medium,
        switchInCurve: AppMotion.standard,
        switchOutCurve: AppMotion.standard,
        transitionBuilder: (child, animation) => FadeTransition(
          opacity: animation,
          child: SlideTransition(
            position: Tween(begin: const Offset(0, 0.08), end: Offset.zero).animate(animation),
            child: child,
          ),
        ),
        child: card,
      ),
    );
  }
}
