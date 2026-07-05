import 'package:flutter_local_notifications/flutter_local_notifications.dart';

/// Thin wrapper over flutter_local_notifications: shows a device notification
/// for a backend-scheduled reminder or alert.
///
/// MetroPulse schedules nothing client-side — every notification shown here
/// surfaces a decision the backend already made (destination, interchange,
/// last-train, leave-home, missed-stop, delay, or a service alert). This
/// delivers reliably whenever the app process is alive (foreground or
/// backgrounded-but-not-killed); delivery while the process has been fully
/// killed needs push notifications (FCM/APNs), which is a real backend
/// integration out of scope for this MVP — not something to fake here.
class NotificationsService {
  NotificationsService() : _plugin = FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;
  bool _initialized = false;

  Future<void> ensureInitialized() async {
    if (_initialized) return;
    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const iOS = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );
    await _plugin.initialize(
      const InitializationSettings(android: android, iOS: iOS),
    );
    // Android 13+ requires an explicit runtime permission request or every
    // notification silently does nothing.
    await _plugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.requestNotificationsPermission();
    _initialized = true;
  }

  Future<void> show({required int id, required String title, required String body}) async {
    await ensureInitialized();
    const details = NotificationDetails(
      android: AndroidNotificationDetails(
        'metropulse_alerts',
        'MetroPulse alerts',
        channelDescription:
            'Destination, interchange, last-train, leave-home and service alerts.',
        importance: Importance.high,
        priority: Priority.high,
      ),
      iOS: DarwinNotificationDetails(),
    );
    await _plugin.show(id, title, body, details);
  }
}
