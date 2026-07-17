import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../core/config.dart';
import '../../core/design/app_colors.dart';
import '../../core/design/app_motion.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/empty_state.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/moment_row.dart';
import '../../core/widgets/shimmer_skeleton.dart';
import '../../providers/core_providers.dart';
import 'notifications_providers.dart';

final _dateFormat = DateFormat('d MMM');

/// The in-app notification inbox: every destination/interchange/last-train/
/// leave-home/missed-stop/delay/service alert the backend has raised for
/// this user, independent of whether a local OS notification also fired.
class NotificationsScreen extends ConsumerStatefulWidget {
  const NotificationsScreen({super.key});

  @override
  ConsumerState<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends ConsumerState<NotificationsScreen> {
  // Optimistic local overlay: ids marked read here render as read
  // immediately, without waiting for (or forcing) a full list re-fetch.
  // The provider is only invalidated on pull-to-refresh or after the bulk
  // "mark all read" action — never on a single-row tap — so the list never
  // flashes a loading shimmer just to flip one row's read state.
  final Set<int> _locallyRead = {};
  bool _markingAll = false;

  bool _isRead(Map<String, dynamic> row) {
    final id = (row['id'] as num).toInt();
    return row['read_at'] != null || _locallyRead.contains(id);
  }

  Future<void> _markOneRead(int id) async {
    if (_locallyRead.contains(id)) return;
    setState(() => _locallyRead.add(id));
    await ref.read(notificationsRepositoryProvider).markRead(id);
  }

  Future<void> _markAllRead(List<Map<String, dynamic>> data) async {
    final unreadIds = data.where((row) => !_isRead(row)).map((row) => (row['id'] as num).toInt()).toList();
    if (unreadIds.isEmpty || _markingAll) return;
    setState(() {
      _markingAll = true;
      _locallyRead.addAll(unreadIds);
    });
    try {
      final repo = ref.read(notificationsRepositoryProvider);
      await Future.wait(unreadIds.map(repo.markRead));
    } finally {
      if (mounted) setState(() => _markingAll = false);
      ref.invalidate(notificationsListProvider);
    }
  }

  Future<void> _refresh() async {
    _locallyRead.clear();
    ref.invalidate(notificationsListProvider);
    await ref.read(notificationsListProvider.future);
  }

  @override
  Widget build(BuildContext context) {
    final notifications = ref.watch(notificationsListProvider);
    final loadedData = notifications.asData?.value;
    final hasUnread = loadedData?.any((row) => !_isRead(row)) ?? false;
    final unreadCount = loadedData?.where((row) => !_isRead(row)).length ?? 0;

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Notifications'),
            if (hasUnread)
              Text(
                '$unreadCount new',
                style: Theme.of(context).textTheme.labelSmall?.copyWith(fontWeight: FontWeight.bold),
              ),
          ],
        ),
        actions: [
          // Single entry point to the Disruption Board — official DMRC alerts
          // and unverified commuter reports — surfaced from the alerts inbox
          // rather than a competing home surface.
          if (AppConfig.disruptionsEnabled)
            Padding(
              padding: const EdgeInsets.only(right: AppSpacing.sm),
              child: IconPillButton(
                icon: Icons.campaign_rounded,
                tooltip: 'Disruptions',
                onPressed: () => context.push('/disruptions'),
              ),
            ),
          if (hasUnread)
            Padding(
              padding: const EdgeInsets.only(right: AppSpacing.sm),
              child: IconPillButton(
                icon: Icons.done_all_rounded,
                tooltip: 'Mark all read',
                onPressed: _markingAll ? null : () => _markAllRead(loadedData!),
              ),
            ),
        ],
      ),
      body: AmbientBackground(
        intensity: 0.4,
        child: SafeArea(
          child: RefreshIndicator(
            onRefresh: _refresh,
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
                    message: "We couldn't load your notifications.",
                    actionLabel: 'Try again',
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
                  : ListView(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      children: [
                        MomentList(
                          children: [
                            for (final row in data) _NotificationRow(
                              row: row,
                              read: _isRead(row),
                              onTap: _isRead(row) ? null : () => _markOneRead((row['id'] as num).toInt()),
                            ),
                          ],
                        ),
                      ],
                    ),
            ),
          ),
        ),
      ),
    );
  }
}

class _NotificationRow extends StatefulWidget {
  const _NotificationRow({required this.row, required this.read, required this.onTap});

  final Map<String, dynamic> row;
  final bool read;
  final VoidCallback? onTap;

  @override
  State<_NotificationRow> createState() => _NotificationRowState();
}

class _NotificationRowState extends State<_NotificationRow> {
  static IconData _iconFor(String kind) => switch (kind) {
        'destination_alert' => Icons.notifications_active_rounded,
        'interchange_reminder' => Icons.transfer_within_a_station_rounded,
        'last_train' => Icons.nightlight_rounded,
        'leave_home' => Icons.directions_walk_rounded,
        'missed_stop' => Icons.error_rounded,
        'journey_delay' => Icons.schedule_rounded,
        'journey_completed' => Icons.check_circle_rounded,
        _ => Icons.info_rounded,
      };

  /// Severity tint for UNREAD rows only, varied by `kind`; read rows always
  /// fall back to [IconBadge]'s neutral default so a cleared notification
  /// stops shouting its original severity.
  static Color? _tintFor(String kind) => switch (kind) {
        'missed_stop' => AppColors.danger,
        'journey_delay' => AppColors.warning,
        'journey_completed' => AppColors.success,
        _ => AppColors.brandBlue,
      };

  String _timeLabel() {
    final time = DateTime.tryParse('${widget.row['created_at']}');
    if (time == null) return '–';
    final local = time.toLocal();
    if (DateUtils.isSameDay(local, DateTime.now())) return clockTime(time);
    return _dateFormat.format(local);
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final read = widget.read;
    final kind = '${widget.row['kind']}';
    final tint = _tintFor(kind);
    final scheme = Theme.of(context).colorScheme;

    final targetBg = read ? scheme.primary.withValues(alpha: 0.14) : (tint ?? scheme.primary).withValues(alpha: 0.16);
    final targetFg = read ? scheme.primary : (tint ?? scheme.primary);
    final icon = _iconFor(kind);

    final badge = reduceMotion
        ? IconBadge(icon: icon, color: targetBg, foreground: targetFg)
        : _AnimatedIconBadge(icon: icon, color: targetBg, foreground: targetFg);

    final title = reduceMotion
        ? Text(
            '${widget.row['title']}',
            style: TextStyle(fontWeight: read ? FontWeight.w500 : FontWeight.w800, fontSize: 15),
          )
        : AnimatedDefaultTextStyle(
            duration: AppMotion.fast,
            curve: AppMotion.standard,
            style: TextStyle(
              fontWeight: read ? FontWeight.w500 : FontWeight.w800,
              fontSize: 15,
              color: Theme.of(context).textTheme.bodyLarge?.color,
            ),
            child: Text('${widget.row['title']}'),
          );

    return MomentRow(
      leading: badge,
      title: title,
      subtitle: Text('${widget.row['body']}', style: Theme.of(context).textTheme.bodyMedium),
      trailing: Text(_timeLabel(), style: Theme.of(context).textTheme.labelSmall),
      onTap: widget.onTap,
    );
  }
}

/// An [IconBadge] whose background/foreground tint cross-fades over
/// [AppMotion.fast] whenever [color]/[foreground] change — used to animate
/// a row's severity tint fading to the neutral "read" tint on mark-read,
/// instead of snapping instantly.
class _AnimatedIconBadge extends ImplicitlyAnimatedWidget {
  const _AnimatedIconBadge({required this.icon, required this.color, required this.foreground})
      : super(duration: AppMotion.fast, curve: AppMotion.standard);

  final IconData icon;
  final Color color;
  final Color foreground;

  @override
  ImplicitlyAnimatedWidgetState<_AnimatedIconBadge> createState() => _AnimatedIconBadgeState();
}

class _AnimatedIconBadgeState extends ImplicitlyAnimatedWidgetState<_AnimatedIconBadge> {
  ColorTween? _color;
  ColorTween? _foreground;

  @override
  void forEachTween(TweenVisitor<dynamic> visitor) {
    _color = visitor(_color, widget.color, (value) => ColorTween(begin: value as Color)) as ColorTween?;
    _foreground =
        visitor(_foreground, widget.foreground, (value) => ColorTween(begin: value as Color)) as ColorTween?;
  }

  @override
  Widget build(BuildContext context) {
    final animation = this.animation;
    return IconBadge(
      icon: widget.icon,
      color: _color?.evaluate(animation),
      foreground: _foreground?.evaluate(animation),
    );
  }
}
