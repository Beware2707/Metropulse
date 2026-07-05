import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/formatters.dart';
import '../../providers/core_providers.dart';
import '../shared/async_section.dart';
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
      body: RefreshIndicator(
        onRefresh: () async => ref.invalidate(notificationsListProvider),
        child: notifications.when(
          loading: () => ListView(
            padding: const EdgeInsets.all(16),
            children: const [
              SkeletonBlock(height: 56),
              SizedBox(height: 8),
              SkeletonBlock(height: 56),
            ],
          ),
          error: (error, _) => ListView(
            children: [
              const SizedBox(height: 64),
              Icon(Icons.cloud_off, size: 48, color: Theme.of(context).colorScheme.outline),
              const SizedBox(height: 12),
              const Center(child: Text('Could not load notifications.')),
              Center(
                child: TextButton(
                  onPressed: () => ref.invalidate(notificationsListProvider),
                  child: const Text('Retry'),
                ),
              ),
            ],
          ),
          data: (data) => data.isEmpty
              ? ListView(
                  children: const [
                    SizedBox(height: 96),
                    Icon(Icons.notifications_none, size: 48),
                    SizedBox(height: 12),
                    Center(child: Text("You're all caught up.")),
                  ],
                )
              : ListView.builder(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  itemCount: data.length,
                  itemBuilder: (_, index) {
                    final row = data[index];
                    final read = row['read_at'] != null;
                    return ListTile(
                      leading: Icon(
                        _iconFor('${row['kind']}'),
                        color: read ? Theme.of(context).colorScheme.outline : null,
                      ),
                      title: Text(
                        '${row['title']}',
                        style: TextStyle(
                            fontWeight: read ? FontWeight.normal : FontWeight.w700),
                      ),
                      subtitle: Text('${row['body']}'),
                      trailing: Text(clockTime(DateTime.tryParse('${row['created_at']}'))),
                      onTap: read
                          ? null
                          : () async {
                              await ref
                                  .read(notificationsRepositoryProvider)
                                  .markRead((row['id'] as num).toInt());
                              ref.invalidate(notificationsListProvider);
                            },
                    );
                  },
                ),
        ),
      ),
    );
  }

  IconData _iconFor(String kind) => switch (kind) {
        'destination_alert' => Icons.notifications_active_outlined,
        'interchange_reminder' => Icons.transfer_within_a_station,
        'last_train' => Icons.nightlight_outlined,
        'leave_home' => Icons.directions_walk,
        'missed_stop' => Icons.error_outline,
        'journey_delay' => Icons.schedule_outlined,
        'journey_completed' => Icons.check_circle_outline,
        _ => Icons.info_outline,
      };
}
