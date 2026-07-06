import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:hive_flutter/hive_flutter.dart';

import 'app.dart';
import 'core/crash_reporting.dart';
import 'core/design/app_colors.dart';
import 'core/design/app_spacing.dart';
import 'data/local_store.dart';

Future<void> main() async {
  // Crash handling: every uncaught error is funnelled through one place
  // (reportError), which prints locally always and additionally uploads to
  // Firebase Crashlytics once a Firebase project is configured -- see
  // docs/firebase_setup.md.
  await runZonedGuarded(() async {
    WidgetsFlutterBinding.ensureInitialized();
    await initializeCrashReporting();
    FlutterError.onError = (details) {
      FlutterError.presentError(details);
      reportError(details.exception, details.stack, fatal: true);
    };
    PlatformDispatcher.instance.onError = (error, stack) {
      reportError(error, stack, fatal: true);
      return true;
    };
    // Framework-level per-widget error boundary: if a widget throws
    // synchronously during build(), Flutter swaps just that subtree for
    // whatever this returns. Without this override it's the default
    // red-and-white "Exception caught" box — ugly and alarming even though
    // the app itself hasn't crashed. `FlutterError.onError` above already
    // reports these (the framework calls it before invoking this builder),
    // so we only render a calm fallback here, not log again.
    ErrorWidget.builder = (details) => const _InlineErrorFallback();
    await Hive.initFlutter();
    final store = await LocalStore.open();
    runApp(
      ProviderScope(
        overrides: [localStoreProvider.overrideWithValue(store)],
        child: const MetroPulseApp(),
      ),
    );
  }, (error, stack) => reportError(error, stack, fatal: true));
}

/// Calm, on-brand replacement for Flutter's default red-and-white
/// "Exception caught" error box, shown in place of any single widget
/// subtree that throws during build().
///
/// `ErrorWidget.builder` has no guaranteed access to an app `Theme` (it can
/// fire before `MaterialApp` mounts, or deep in a broken tree), so this is
/// deliberately self-contained: plain Material widgets, its own
/// `Directionality`/`Material` ancestors, and fixed brand colours (rather
/// than `Theme.of(context)`) that read fine on both light and dark
/// backgrounds. Mirrors the tone/shape of [EmptyState] without depending on
/// it, since that widget assumes a full theme is available.
class _InlineErrorFallback extends StatelessWidget {
  const _InlineErrorFallback();

  @override
  Widget build(BuildContext context) {
    return const Directionality(
      textDirection: TextDirection.ltr,
      child: Material(
        color: AppColors.darkSurfaceElevated,
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.lg),
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.error_outline_rounded, color: AppColors.darkTextSecondary, size: 28),
                SizedBox(height: AppSpacing.sm),
                Text(
                  'Something went wrong here',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.darkTextSecondary, fontSize: 13),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
