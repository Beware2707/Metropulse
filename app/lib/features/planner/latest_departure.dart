import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/moment_row.dart';
import '../../providers/core_providers.dart';

/// The latest-safe-departure fact for an (origin, destination) pair, from
/// GET /api/v1/journeys/latest-departure. Null when the backend has no
/// answer (unknown stops, no same-service-day path, offline) — which simply
/// hides the row rather than surfacing an error.
final latestDepartureProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>?, ({String origin, String destination})>(
        (ref, pair) {
  return ref
      .watch(journeyRepositoryProvider)
      .latestDeparture(pair.origin, pair.destination);
});

/// A low-key "Latest you can leave: HH:MM" row under a computed plan.
/// Tapping it opens a sheet with the depart-by time large, the arrive-by
/// time, and each leg's last feasible boarding time. Renders nothing while
/// loading, on error, or when the backend has no answer.
class LatestDepartureRow extends ConsumerWidget {
  const LatestDepartureRow({
    super.key,
    required this.origin,
    required this.destination,
  });

  final String origin;
  final String destination;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final data = ref
        .watch(latestDepartureProvider((origin: origin, destination: destination)))
        .valueOrNull;
    final departBy = DateTime.tryParse('${data?['depart_by'] ?? ''}');
    if (data == null || departBy == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return MomentRow(
      leading: const IconBadge(icon: Icons.schedule_rounded),
      title: Text(
        'Latest you can leave: ${clockTime(departBy)}',
        style: theme.textTheme.titleMedium,
      ),
      subtitle: Text('From the published timetable', style: theme.textTheme.bodySmall),
      onTap: () => showAppBottomSheet<void>(
        context,
        builder: (_) => _LatestDepartureSheet(data: data),
      ),
    );
  }
}

/// The expanded story: depart-by large, arrive-by, per-leg last boarding
/// times, and the honest published-timetable caveat.
class _LatestDepartureSheet extends StatelessWidget {
  const _LatestDepartureSheet({required this.data});

  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final departBy = DateTime.tryParse('${data['depart_by'] ?? ''}');
    final arriveBy = DateTime.tryParse('${data['arrive_by'] ?? ''}');
    final totalMinutes = data['total_minutes'] as int?;
    final legs = (data['legs'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .toList(growable: false);
    return Padding(
      padding: const EdgeInsets.fromLTRB(
          AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xxl),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('LEAVE BY', style: theme.textTheme.labelSmall),
          Text(clockTime(departBy), style: theme.textTheme.displaySmall),
          if (arriveBy != null)
            Text(
              'Arrive by ${clockTime(arriveBy)}'
              '${totalMinutes != null ? ' · $totalMinutes min' : ''}',
              style: theme.textTheme.bodyMedium,
            ),
          if (legs.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.lg),
            MomentList(children: [for (final leg in legs) _LegRow(leg: leg)]),
          ],
          const SizedBox(height: AppSpacing.lg),
          Text(
            'From the published timetable — leave margin for gate queues.',
            style: theme.textTheme.bodySmall
                ?.copyWith(color: theme.colorScheme.outline),
          ),
        ],
      ),
    );
  }
}

class _LegRow extends StatelessWidget {
  const _LegRow({required this.leg});

  final Map<String, dynamic> leg;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final lastDeparture = DateTime.tryParse('${leg['last_departure'] ?? ''}');
    final headsign = leg['headsign'] as String?;
    return MomentRow(
      leading: const IconBadge(icon: Icons.directions_subway_filled),
      title: Text(
        'Board at ${leg['board_name'] ?? leg['board_stop_id']} '
        'by ${clockTime(lastDeparture)}',
        style: theme.textTheme.titleMedium,
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LineChip(
            label: cleanLineName(leg['route_long_name'] as String?),
            colorHex: leg['route_color'] as String?,
            dense: true,
          ),
          const SizedBox(height: 3),
          Text(
            '${headsign != null && headsign.isNotEmpty ? 'towards $headsign · ' : ''}'
            'alight at ${leg['alight_name'] ?? leg['alight_stop_id']}',
            style: theme.textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
