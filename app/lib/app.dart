import 'dart:async';

import 'package:dynamic_color/dynamic_color.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/router.dart';
import 'core/theme.dart';
import 'data/ws_client.dart';
import 'features/home/home_providers.dart';
import 'features/notifications/notifications_providers.dart';
import 'features/settings/settings_providers.dart';
import 'l10n/gen/app_localizations.dart';
import 'providers/core_providers.dart';
import 'providers/live_providers.dart';

/// Root widget: themed MaterialApp driven by GoRouter and the theme setting.
///
/// Also owns app-lifecycle hygiene: the WebSocket is dropped while the app
/// is backgrounded and resumed (with seq replay) on foreground, and the
/// notification inbox is synced on resume plus periodically while
/// foregrounded so backend-scheduled alerts surface promptly. The
/// notification poll timer itself is paused/resumed in step with the
/// WebSocket, so it doesn't keep firing (and burning battery/network) while
/// backgrounded.
class MetroPulseApp extends ConsumerStatefulWidget {
  const MetroPulseApp({super.key});

  @override
  ConsumerState<MetroPulseApp> createState() => _MetroPulseAppState();
}

class _MetroPulseAppState extends ConsumerState<MetroPulseApp>
    with WidgetsBindingObserver {
  Timer? _notificationTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _startNotificationTimer();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(notificationsSyncControllerProvider).sync();
      // Daily-usage basis. A no-op unless the rider has opted in.
      ref.read(analyticsServiceProvider).recordAppOpened();
    });
  }

  void _startNotificationTimer() {
    _notificationTimer ??= Timer.periodic(
      const Duration(seconds: 20),
      (_) => ref.read(notificationsSyncControllerProvider).sync(),
    );
  }

  void _stopNotificationTimer() {
    _notificationTimer?.cancel();
    _notificationTimer = null;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _stopNotificationTimer();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final ws = ref.read(wsClientProvider);
    switch (state) {
      case AppLifecycleState.paused || AppLifecycleState.detached:
        ws.suspend();
        _stopNotificationTimer();
        // Backgrounding is the last reliable moment to send: the buffer is
        // in-memory only, so anything still held when the OS reclaims the
        // process is gone.
        unawaited(ref.read(analyticsServiceProvider).flush());
      case AppLifecycleState.resumed:
        ws.resume();
        _startNotificationTimer();
        ref.read(notificationsSyncControllerProvider).sync();
        ref.read(analyticsServiceProvider).recordAppOpened();
      case AppLifecycleState.inactive || AppLifecycleState.hidden:
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    final themeMode = ref.watch(themeModeProvider);
    final router = ref.watch(routerProvider);
    final highContrast = ref.watch(highContrastProvider);
    final dynamicColorEnabled = ref.watch(dynamicColorEnabledProvider);
    final textScale = ref.watch(textScaleFactorProvider);
    final locale = ref.watch(localeProvider);

    // Once the socket comes back up after a drop, refresh the REST-backed
    // data that has no push channel of its own (a one-shot FutureProvider
    // otherwise stays exactly as stale as it was when the connection died).
    ref.listen(wsStatusProvider, (previous, next) {
      if (previous?.valueOrNull == WsStatus.reconnecting && next.valueOrNull == WsStatus.live) {
        ref
          ..invalidate(activeJourneyProvider)
          ..invalidate(commuteCardProvider);
      }
    });

    // The OS reporting connectivity restored is a much faster, more direct
    // signal than waiting for the WS's own exponential backoff to happen to
    // land on a retry — nudge it the moment a tunnel exit is detected.
    ref.listen(isOnlineProvider, (previous, next) {
      if (previous?.valueOrNull == false && next.valueOrNull == true) {
        ref.read(wsClientProvider).reconnectNow();
      }
    });

    return DynamicColorBuilder(
      builder: (lightDynamic, darkDynamic) {
        return MaterialApp.router(
          title: 'MetroPulse',
          debugShowCheckedModeBanner: false,
          theme: buildLightTheme(
            highContrast: highContrast,
            dynamicScheme: dynamicColorEnabled ? lightDynamic : null,
          ),
          darkTheme: buildDarkTheme(
            highContrast: highContrast,
            dynamicScheme: dynamicColorEnabled ? darkDynamic : null,
          ),
          themeMode: themeMode,
          routerConfig: router,
          locale: locale,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          builder: (context, child) {
            if (child == null) return const SizedBox.shrink();
            // Compose the OS text-scale setting with the user's in-app
            // multiplier (Settings > Accessibility), clamped to stay legible.
            final mediaQuery = MediaQuery.of(context);
            final combinedScale =
                (mediaQuery.textScaler.scale(1.0) * textScale).clamp(0.8, 3.0);
            return MediaQuery(
              data: mediaQuery.copyWith(textScaler: TextScaler.linear(combinedScale)),
              child: child,
            );
          },
        );
      },
    );
  }
}
