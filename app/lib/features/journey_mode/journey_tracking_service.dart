// The foreground service that follows a rider along their route.
//
// Rider-initiated and rider-stoppable, always. Tracking starts because
// somebody tapped "Start journey" while looking at the app, and the ongoing
// notification carries a Stop button, so it can never become something that
// happens *to* a rider.
//
// That is also what keeps MetroPulse out of Play's background-location review:
// a foreground service may read location without ACCESS_BACKGROUND_LOCATION,
// because the persistent notification is the user-visible signal that replaces
// it. The moment tracking could start without the rider asking, that stops
// being true — see the note in AndroidManifest.xml.
//
// The decision logic lives in `domain/journey_tracking.dart` and
// `domain/tracking_notification.dart` so it is testable off-device; this file
// is plumbing and should stay that way.

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:geolocator/geolocator.dart';

import '../../domain/journey_tracking.dart';
import '../../domain/motion_stop_counter.dart';
import '../../domain/tracking_notification.dart';

/// Keys for the station list handed to the isolate. The task handler runs in
/// a SEPARATE isolate with no access to providers, so everything it needs has
/// to be serialised across.
const _kStationsKey = 'tracking_stations';
const _kStopIdKey = 'tracking_journey_id';

/// Starts and stops journey tracking.
class JourneyTrackingService {
  /// Whether tracking is running right now.
  static Future<bool> get isRunning => FlutterForegroundTask.isRunningService;

  /// One-time channel setup. Safe to call repeatedly.
  static void configure() {
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'metropulse_journey',
        channelName: 'Journey tracking',
        channelDescription:
            'Shows your next station while a journey is running.',
        // Low importance: this notification is meant to be glanced at, not to
        // buzz. The rider is on a train; interrupting them every 20 seconds
        // would make them turn the whole feature off.
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.LOW,
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(),
      foregroundTaskOptions: ForegroundTaskOptions(
        // 15 s: a Delhi Metro run between stations is minutes, so this is
        // frequent enough to catch an approach and slow enough not to drain
        // a battery the rider needs for the rest of their day.
        eventAction: ForegroundTaskEventAction.repeat(15000),
        autoRunOnBoot: false,
        allowWakeLock: true,
        allowWifiLock: false,
      ),
    );
  }

  /// Begin tracking. Returns false when the rider declined a permission —
  /// which is a legitimate answer, not an error to shout about.
  static Future<bool> start({
    required int journeyId,
    required List<TrackedStation> stations,
  }) async {
    if (stations.isEmpty) return false;

    if (!await _ensurePermissions()) return false;

    configure();
    await FlutterForegroundTask.saveData(
      key: _kStationsKey,
      value: _encodeStations(stations),
    );
    await FlutterForegroundTask.saveData(key: _kStopIdKey, value: journeyId);

    final result = await FlutterForegroundTask.startService(
      serviceTypes: const [ForegroundServiceTypes.location],
      notificationTitle: 'Following your journey',
      notificationText: 'Getting your location…',
      notificationButtons: [
        // The rider must always be one tap from ending this.
        const NotificationButton(id: 'stop', text: 'Stop'),
      ],
      callback: startJourneyTracking,
    );
    return result is ServiceRequestSuccess;
  }

  static Future<void> stop() => FlutterForegroundTask.stopService();

  static Future<bool> _ensurePermissions() async {
    // Notifications first: a foreground service whose notification is blocked
    // is a service the rider cannot see or stop.
    final notification = await FlutterForegroundTask.checkNotificationPermission();
    if (notification != NotificationPermission.granted) {
      final asked = await FlutterForegroundTask.requestNotificationPermission();
      if (asked != NotificationPermission.granted) return false;
    }

    var permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    // whileInUse is enough, and is all we ask for. `always` would be the
    // background-location permission we are deliberately not requesting.
    return permission == LocationPermission.whileInUse ||
        permission == LocationPermission.always;
  }

  static List<Map<String, Object?>> _encodeStations(
          List<TrackedStation> stations) =>
      [
        for (final s in stations)
          {
            'stop_id': s.stopId,
            'name': s.name,
            'lat': s.lat,
            'lon': s.lon,
            'underground': s.underground,
          },
      ];
}

/// Isolate entry point. Must be a top-level function with this pragma or the
/// AOT compiler will tree-shake it away and the service will start into
/// nothing.
@pragma('vm:entry-point')
void startJourneyTracking() {
  FlutterForegroundTask.setTaskHandler(_JourneyTaskHandler());
}

class _JourneyTaskHandler extends TaskHandler {
  JourneyTracker? _tracker;
  final MotionStopCounter _stops = MotionStopCounter();
  StreamSubscription<Position>? _positions;
  Position? _latest;

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    final raw = await FlutterForegroundTask.getData<List<dynamic>>(
        key: _kStationsKey);
    final stations = [
      for (final entry in raw ?? const [])
        if (entry is Map)
          TrackedStation(
            stopId: '${entry['stop_id']}',
            name: '${entry['name']}',
            lat: (entry['lat'] as num).toDouble(),
            lon: (entry['lon'] as num).toDouble(),
            underground: entry['underground'] == true,
          ),
    ];
    _tracker = JourneyTracker(stations: stations);

    _positions = Geolocator.getPositionStream(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        // A metro train covers ground fast; 25 m keeps updates meaningful
        // without waking the radio for every footstep on a platform.
        distanceFilter: 25,
      ),
    ).listen(
      (position) => _latest = position,
      // A stream error underground is expected, not exceptional. Keep the
      // service alive and let the tracker fall back to counted stops.
      onError: (Object _) => _latest = null,
    );
  }

  @override
  void onRepeatEvent(DateTime timestamp) {
    final tracker = _tracker;
    if (tracker == null) return;

    final position = _latest;
    final update = tracker.update(
      fix: position == null
          ? null
          : RiderFix(
              lat: position.latitude,
              lon: position.longitude,
              accuracyMeters: position.accuracy,
              at: position.timestamp,
            ),
      now: timestamp,
      stopsCounted: _stops.stops,
    );

    final note = buildTrackingNotification(update);
    FlutterForegroundTask.updateService(
      notificationTitle: note.title,
      notificationText: note.body,
    );
    // Let the UI mirror the notification when the app is open.
    FlutterForegroundTask.sendDataToMain({
      'next': update.nextStation?.name,
      'remaining': update.stationsRemaining,
      'source': update.source.name,
      'approaching': update.isApproaching,
    });
  }

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {
    await _positions?.cancel();
    _positions = null;
  }

  @override
  void onNotificationButtonPressed(String id) {
    if (id == 'stop') FlutterForegroundTask.stopService();
  }

  @override
  void onNotificationPressed() {
    FlutterForegroundTask.launchApp('/journey');
  }
}

/// Debug aid: the handler runs in another isolate, so an exception there is
/// invisible in the normal console.
void debugLogTracking(Object message) {
  if (kDebugMode) debugPrint('[tracking] $message');
}
