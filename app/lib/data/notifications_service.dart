import 'package:flutter_local_notifications/flutter_local_notifications.dart';
// timezone ships as a resolved (transitive) dependency of
// flutter_local_notifications; zonedSchedule needs a TZDateTime, which only
// this package can construct. No new pubspec dependency is introduced.
// ignore: depend_on_referenced_packages
import 'package:timezone/timezone.dart' as tz;

/// Thin wrapper over flutter_local_notifications: shows a device notification
/// for a backend-scheduled reminder or alert, and — for the one case the
/// commuter opts into explicitly — schedules a single local reminder at a
/// computed future time.
///
/// Almost everything here surfaces a decision the backend already made
/// (destination, interchange, last-train, leave-home, missed-stop, delay, or
/// a service alert). The one client-scheduled case is the last-train
/// reminder ([scheduleAt]): the backend reminder is the reliable path, and
/// this adds an on-device alert as a belt-and-braces convenience. Local
/// delivery is dependable while the app process is alive (foreground or
/// backgrounded-but-not-killed); delivery while the process has been fully
/// killed needs push notifications (FCM/APNs), a real backend integration out
/// of scope for this MVP — not something to fake here.
class NotificationsService {
  NotificationsService() : _plugin = FlutterLocalNotificationsPlugin();

  final FlutterLocalNotificationsPlugin _plugin;
  bool _initialized = false;

  static const NotificationDetails _details = NotificationDetails(
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
    _initialized = true;
  }

  /// Requests the OS notification permission and returns whether it's
  /// granted. Android 13+ and iOS both gate delivery on this; a denied
  /// result lets callers stay honest ("we couldn't set a device alert")
  /// instead of pretending a reminder is armed.
  Future<bool> requestPermission() async {
    await ensureInitialized();
    final android = _plugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
    if (android != null) {
      return await android.requestNotificationsPermission() ?? false;
    }
    final iOS = _plugin
        .resolvePlatformSpecificImplementation<IOSFlutterLocalNotificationsPlugin>();
    if (iOS != null) {
      return await iOS.requestPermissions(alert: true, badge: true, sound: true) ??
          false;
    }
    return true;
  }

  Future<void> show({required int id, required String title, required String body}) async {
    await ensureInitialized();
    await requestPermission();
    await _plugin.show(id, title, body, _details);
  }

  /// Schedules a one-off local notification to fire at the absolute instant
  /// [when]. Returns true only when the OS accepted the schedule; false when
  /// permission is denied, the time is already past, or the platform can't
  /// schedule — so the caller can tell the user the honest truth. Constructs
  /// the fire time in UTC, which is timezone-correct regardless of the
  /// device's local zone because [when] is an absolute instant.
  Future<bool> scheduleAt({
    required int id,
    required String title,
    required String body,
    required DateTime when,
  }) async {
    if (!when.isAfter(DateTime.now())) return false;
    try {
      await ensureInitialized();
      if (!await requestPermission()) return false;
      final scheduled = tz.TZDateTime.from(when.toUtc(), tz.UTC);
      await _plugin.zonedSchedule(
        id,
        title,
        body,
        scheduled,
        _details,
        androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
        uiLocalNotificationDateInterpretation:
            UILocalNotificationDateInterpretation.absoluteTime,
      );
      return true;
    } catch (_) {
      // Any platform/permission failure is reported as "not scheduled" so
      // the UI degrades honestly rather than throwing.
      return false;
    }
  }
}
