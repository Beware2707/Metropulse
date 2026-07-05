import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/core_providers.dart';

/// Boot: register the device, warm the offline cache, then enter the app.
/// Both steps tolerate being offline — the cache is the offline story.
class SplashScreen extends ConsumerStatefulWidget {
  const SplashScreen({super.key});

  @override
  ConsumerState<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _boot();
  }

  Future<void> _boot() async {
    try {
      await ref.read(apiClientProvider).ensureRegistered();
    } on Exception {
      // Offline start: cached data still works; auth recovers on reconnect.
    }
    await ref.read(offlineBundleProvider.future);
    if (mounted) context.go('/');
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.directions_subway_filled, size: 72, color: scheme.primary),
            const SizedBox(height: 16),
            Text('MetroPulse',
                style: Theme.of(context).textTheme.headlineMedium),
            const SizedBox(height: 24),
            const SizedBox(
              width: 28,
              height: 28,
              child: CircularProgressIndicator(strokeWidth: 3),
            ),
          ],
        ),
      ),
    );
  }
}
