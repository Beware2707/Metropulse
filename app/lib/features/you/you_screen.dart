import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/moment_row.dart';
import '../notifications/notifications_providers.dart';

/// "You": everything personal — favourites, where you've been (trip history
/// and Commute Replay), notifications, settings — behind one tab instead of
/// four. Each row pushes straight to the existing full screen; this is a
/// hub, not a rebuild of any of them.
class YouScreen extends ConsumerWidget {
  const YouScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    final notifications = ref.watch(notificationsListProvider);
    final hasUnread = notifications.asData?.value.any((row) => row['read_at'] == null) ?? false;
    return Scaffold(
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 140),
            children: [
              Text('You', style: theme.textTheme.displaySmall),
              const SizedBox(height: AppSpacing.xl),
              MomentList(
                children: [
                  MomentRow(
                    leading: const IconBadge(icon: Icons.star_rounded),
                    title: Text('Favourites', style: theme.textTheme.titleMedium),
                    subtitle: Text('Home, Work, and pinned journeys', style: theme.textTheme.bodyMedium),
                    onTap: () => context.push('/favourites'),
                  ),
                  MomentRow(
                    leading: const IconBadge(icon: Icons.history_rounded),
                    title: Text("Where you've been", style: theme.textTheme.titleMedium),
                    subtitle: Text('Trip history and Commute Replay', style: theme.textTheme.bodyMedium),
                    onTap: () => context.push('/journeys/history'),
                  ),
                  MomentRow(
                    leading: const IconBadge(icon: Icons.notifications_none_rounded),
                    title: Text('Notifications', style: theme.textTheme.titleMedium),
                    subtitle: Text('Alerts and updates', style: theme.textTheme.bodyMedium),
                    trailing: hasUnread
                        ? Container(
                            width: 8,
                            height: 8,
                            decoration: const BoxDecoration(color: AppColors.danger, shape: BoxShape.circle),
                          )
                        : null,
                    onTap: () => context.push('/notifications'),
                  ),
                  MomentRow(
                    leading: const IconBadge(icon: Icons.settings_rounded),
                    title: Text('Settings', style: theme.textTheme.titleMedium),
                    subtitle: Text('Appearance, accessibility, privacy', style: theme.textTheme.bodyMedium),
                    onTap: () => context.push('/settings'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
