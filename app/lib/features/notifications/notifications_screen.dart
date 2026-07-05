import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/shimmer_skeleton.dart';
import '../../providers/core_providers.dart';
import 'notifications_providers.dart';

/// The in-app notification inbox: every destination/interchange/last-train/
/// leave-home/missed-stop/delay/service alert the backend has raised for
/// this user, independent of whether a local OS notification also fired.
class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notifications = ref.watch(notificationsListProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
      body: AmbientBackground(
        intensity: 0.4,
        child: SafeArea(
          child: RefreshIndicator(
            onRefresh: () async => ref.invalidate(notificationsListProvider),
            child: notifications.when(
              loading: () => ListView(
                padding: const EdgeInsets.all(AppSpacing.lg),
                children: const [
                  ShimmerBlock(height: 76),
                  SizedBox(height: AppSpacing.sm),
                  ShimmerBlock(height: 76),
                ],
              ),
              error: (error, _) => ListView(
                padding: const EdgeInsets.all(AppSpacing.lg),
                children: [
                  const SizedBox(height: 64),
                  EmptyState(
                    icon: Icons.cloud_off_rounded,
                    message: 'Could not load notifications.',
                    actionLabel: 'Retry',
                    onAction: () => ref.invalidate(notificationsListProvider),
                  ),
                ],
              ),
              data: (data) => data.isEmpty
                  ? ListView(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      children: const [
                        SizedBox(height: 96),
                        EmptyState(icon: Icons.notifications_none_rounded, message: "You're all caught up."),
                      ],
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      itemCount: data.length,
                      separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
                      itemBuilder: (_, index) {
                        final row = data[index];
                        final read = row['read_at'] != null;
                        return GlassSurface(
                          onTap: read
                              ? null
                              : () async {
                                  await ref.read(notificationsRepositoryProvider).markRead((row['id'] as num).toInt());
                                  ref.invalidate(notificationsListProvider);
                                },
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              IconBadge(
                                icon: _iconFor('${row['kind']}'),
                                color: read ? null : AppColors.brandBlue.withValues(alpha: 0.16),
                                foreground: read ? null : AppColors.brandBlue,
                              ),
                              const SizedBox(width: AppSpacing.md),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      '${row['title']}',
                                      style: TextStyle(
                                          fontWeight: read ? FontWeight.w500 : FontWeight.w800, fontSize: 15),
                                    ),
                                    Text('${row['body']}', style: Theme.of(context).textTheme.bodyMedium),
                                  ],
                                ),
                              ),
                              Text(clockTime(DateTime.tryParse('${row['created_at']}')),
                                  style: Theme.of(context).textTheme.labelSmall),
                            ],
                          ),
                        );
                      },
                    ),
            ),
          ),
        ),
      ),
    );
  }

  IconData _iconFor(String kind) => switch (kind) {
        'destination_alert' => Icons.notifications_active_rounded,
        'interchange_reminder' => Icons.transfer_within_a_station_rounded,
        'last_train' => Icons.nightlight_rounded,
        'leave_home' => Icons.directions_walk_rounded,
        'missed_stop' => Icons.error_rounded,
        'journey_delay' => Icons.schedule_rounded,
        'journey_completed' => Icons.check_circle_rounded,
        _ => Icons.info_rounded,
      };
}
