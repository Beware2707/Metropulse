import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/router.dart';
import 'core/theme.dart';
import 'l10n/gen/app_localizations.dart';
import 'providers/core_providers.dart';
import 'providers/live_providers.dart';

/// Root widget: themed MaterialApp driven by GoRouter and the theme setting.
///
/// Also owns app-lifecycle battery hygiene: the WebSocket is dropped while
/// the app is backgrounded and resumed (with seq replay) on foreground.
class MetroPulseApp extends ConsumerStatefulWidget {
  const MetroPulseApp({super.key});

  @override
  ConsumerState<MetroPulseApp> createState() => _MetroPulseAppState();
}

class _MetroPulseAppState extends ConsumerState<MetroPulseApp>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final ws = ref.read(wsClientProvider);
    switch (state) {
      case AppLifecycleState.paused || AppLifecycleState.detached:
        ws.suspend();
      case AppLifecycleState.resumed:
        ws.resume();
      case AppLifecycleState.inactive || AppLifecycleState.hidden:
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    final themeMode = ref.watch(themeModeProvider);
    final router = ref.watch(routerProvider);
    return MaterialApp.router(
      title: 'MetroPulse',
      debugShowCheckedModeBanner: false,
      theme: buildLightTheme(),
      darkTheme: buildDarkTheme(),
      themeMode: themeMode,
      routerConfig: router,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
    );
  }
}
