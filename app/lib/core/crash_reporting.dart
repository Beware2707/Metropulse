import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_crashlytics/firebase_crashlytics.dart';
import 'package:flutter/foundation.dart';

/// True once Firebase has actually initialized. Crash reports are only ever
/// sent when this is true, so a developer who hasn't set up their own
/// Firebase project yet (see docs/firebase_setup.md) just sees local
/// debugPrint output instead of the app failing to start.
bool _crashlyticsReady = false;

/// Initializes Firebase Crashlytics if platform config is present.
///
/// No-ops entirely on web (Crashlytics doesn't support it -- the live map
/// preview this app is developed against is unaffected either way) and
/// swallows any initialization failure, since the most common failure mode
/// during development is simply "no google-services.json /
/// GoogleService-Info.plist yet", not a real bug.
Future<void> initializeCrashReporting() async {
  if (kIsWeb) return;
  try {
    await Firebase.initializeApp();
    // Local/debug builds stay noisy in the console instead of the
    // dashboard; only release builds actually upload.
    await FirebaseCrashlytics.instance.setCrashlyticsCollectionEnabled(!kDebugMode);
    _crashlyticsReady = true;
  } on Exception catch (error) {
    debugPrint('Crashlytics not configured yet, skipping: $error');
  }
}

/// Records an error to Crashlytics when it's ready, and always prints it
/// locally too -- the single funnel every uncaught error and reported
/// exception in the app passes through.
void reportError(Object error, StackTrace? stack, {bool fatal = false}) {
  debugPrint('${fatal ? 'FATAL' : 'ERROR'}: $error\n$stack');
  if (_crashlyticsReady) {
    FirebaseCrashlytics.instance.recordError(error, stack, fatal: fatal);
  }
}
