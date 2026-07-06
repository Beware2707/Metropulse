import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/replay_stat.dart';
import '../../core/widgets/section_header.dart';
import '../../core/widgets/shimmer_skeleton.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/station.dart';
import '../../providers/core_providers.dart';

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

/// "This Month" at the top of history: nothing shown until there's at least
/// one trip to report on — an all-zero card would read as broken, not
/// honest.
class _MonthlyReplayHeader extends ConsumerWidget {
  const _MonthlyReplayHeader();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final monthly = ref.watch(monthlyReplayProvider).valueOrNull;
    if (monthly == null || monthly.tripCount == 0) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final stats = <Widget>[
      ReplayStat(icon: Icons.route_rounded, label: 'Trips', value: '${monthly.tripCount}'),
      if (monthly.totalTimeSavedSeconds > 0)
        ReplayStat(
          icon: Icons.bolt_rounded,
          label: 'Saved vs. cab',
          value: minutesLabel(monthly.totalTimeSavedSeconds),
          color: AppColors.success,
        ),
      if (monthly.totalMoneySavedRupees > 0)
        ReplayStat(
          icon: Icons.savings_outlined,
          label: 'Money saved',
          value: '₹${monthly.totalMoneySavedRupees}',
          color: AppColors.success,
        ),
      if (monthly.totalCo2SavedKg > 0)
        ReplayStat(
          icon: Icons.eco_outlined,
          label: 'Carbon saved',
          value: '${monthly.totalCo2SavedKg.toStringAsFixed(1)} kg',
          color: AppColors.success,
        ),
    ];

    return Padding(
      padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 0),
      child: GlassSurface(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('THIS MONTH', style: theme.textTheme.labelMedium),
            const SizedBox(height: AppSpacing.md),
            Wrap(spacing: AppSpacing.xl, runSpacing: AppSpacing.md, children: stats),
          ],
        ),
      ),
    );
  }
}
