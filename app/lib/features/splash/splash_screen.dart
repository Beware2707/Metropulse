import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
import '../../core/widgets/ambient_background.dart';
import '../../providers/core_providers.dart';

/// Boot: register the device, warm the offline cache, then enter the app.
/// Both steps tolerate being offline — the cache is the offline story. The
/// entrance itself is the app's first-ten-seconds moment: a gradient
/// wordmark that breathes in over the ambient backdrop.
class SplashScreen extends ConsumerStatefulWidget {
  const SplashScreen({super.key});

  @override
  ConsumerState<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<SplashScreen> with SingleTickerProviderStateMixin {
  late final AnimationController _controller =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..forward();

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
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: AmbientBackground(
        intensity: 1.4,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ScaleTransition(
                scale: CurvedAnimation(parent: _controller, curve: Curves.elasticOut),
                child: Container(
                  width: 96,
                  height: 96,
                  decoration: BoxDecoration(
                    gradient: AppColors.heroGradientFor(),
                    borderRadius: AppRadius.xlR,
                    boxShadow: [
                      BoxShadow(
                        color: AppColors.brandViolet.withValues(alpha: 0.45),
                        blurRadius: 40,
                        offset: const Offset(0, 16),
                      ),
                    ],
                  ),
                  child: const Icon(Icons.directions_subway_filled, color: Colors.white, size: 48),
                ),
              ),
              const SizedBox(height: 28),
              FadeTransition(
                opacity: CurvedAnimation(parent: _controller, curve: const Interval(0.4, 1.0, curve: Curves.easeOut)),
                child: ShaderMask(
                  shaderCallback: (rect) => AppColors.heroGradientFor().createShader(rect),
                  child: Text('MetroPulse',
                      style: theme.textTheme.displaySmall?.copyWith(color: Colors.white)),
                ),
              ),
              const SizedBox(height: 8),
              FadeTransition(
                opacity: CurvedAnimation(parent: _controller, curve: const Interval(0.6, 1.0, curve: Curves.easeOut)),
                child: Text('Your Delhi Metro companion', style: theme.textTheme.bodyMedium),
              ),
              const SizedBox(height: 40),
              FadeTransition(
                opacity: CurvedAnimation(parent: _controller, curve: const Interval(0.7, 1.0, curve: Curves.easeOut)),
                child: const SizedBox(width: 120, child: _PulseBar()),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PulseBar extends StatefulWidget {
  const _PulseBar();

  @override
  State<_PulseBar> createState() => _PulseBarState();
}

class _PulseBarState extends State<_PulseBar> with SingleTickerProviderStateMixin {
  late final AnimationController _controller =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1100))..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: SizedBox(
        height: 4,
        child: Stack(
          children: [
            ColoredBox(color: scheme.surfaceContainerHighest),
            AnimatedBuilder(
              animation: _controller,
              builder: (context, _) => FractionallySizedBox(
                widthFactor: 0.4,
                alignment: Alignment(-1 + _controller.value * 2.8, 0),
                child: DecoratedBox(decoration: BoxDecoration(gradient: AppColors.heroGradientFor())),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
