import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/notifications_service.dart';
import '../../providers/core_providers.dart';

final notificationsServiceProvider =
    Provider<NotificationsService>((ref) => NotificationsService());

/// The notification inbox, for the in-app notifications list.
final notificationsListProvider = FutureProvider<List<Map<String, dynamic>>>(
  (ref) => ref.watch(notificationsRepositoryProvider).list(),
);

/// Pulls the backend's notification inbox and surfaces anything new as a
/// local OS notification — call [sync] on app resume and periodically while
/// foregrounded (wired in `app.dart`).
class NotificationsSyncController {
  NotificationsSyncController(this._ref);

  final Ref _ref;
  bool _syncing = false;

  Future<void> sync() async {
    if (_syncing) return;
    _syncing = true;
    try {
      final store = _ref.read(localStoreProvider);
      if (!store.notificationsEnabled) return;
      final rows = await _ref.read(notificationsRepositoryProvider).list(limit: 20);
      final lastSeen = store.lastSeenNotificationId;
      final fresh = rows
          .where((row) => ((row['id'] as num?)?.toInt() ?? 0) > lastSeen)
          .toList();
      if (fresh.isEmpty) return;

      final service = _ref.read(notificationsServiceProvider);
      // Oldest-first so notifications appear in the order they happened.
      for (final row in fresh.reversed) {
        await service.show(
          id: (row['id'] as num).toInt(),
          title: '${row['title']}',
          body: '${row['body']}',
        );
      }
      final maxId = rows
          .map((r) => (r['id'] as num?)?.toInt() ?? 0)
          .fold(lastSeen, (a, b) => a > b ? a : b);
      await store.saveLastSeenNotificationId(maxId);
      _ref.invalidate(notificationsListProvider);
    } on Exception {
      // Best-effort: a sync failure must never crash the app; the next
      // resume or periodic tick retries.
    } finally {
      _syncing = false;
    }
  }
}

final notificationsSyncControllerProvider =
    Provider<NotificationsSyncController>((ref) => NotificationsSyncController(ref));
