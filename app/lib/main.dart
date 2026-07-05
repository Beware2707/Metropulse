import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'app.dart';
import 'data/local_store.dart';

Future<void> main() async {
  // Crash handling: every uncaught error is funnelled through one place.
  // debugPrint today; swap `_reportError` for Crashlytics/Sentry at release.
  await runZonedGuarded(() async {
    WidgetsFlutterBinding.ensureInitialized();
    FlutterError.onError = (details) {
      FlutterError.presentError(details);
      _reportError(details.exception, details.stack);
    };
    PlatformDispatcher.instance.onError = (error, stack) {
      _reportError(error, stack);
      return true;
    };
    await Hive.initFlutter();
    final store = await LocalStore.open();
    runApp(
      ProviderScope(
        overrides: [localStoreProvider.overrideWithValue(store)],
        child: const MetroPulseApp(),
      ),
    );
  }, _reportError);
}

void _reportError(Object error, StackTrace? stack) {
  debugPrint('UNCAUGHT: $error\n$stack');
}
