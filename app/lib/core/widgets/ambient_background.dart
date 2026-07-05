import 'package:flutter/material.dart';

import '../design/app_colors.dart';

/// A soft ambient gradient-blob backdrop — the premium "not just a flat
/// colour" canvas behind hero screens (Home, Splash, Journey Mode). Cheap:
/// three blurred, decoratively positioned radial gradients, no images.
class AmbientBackground extends StatelessWidget {
  const AmbientBackground({super.key, this.child, this.intensity = 1.0});

  final Widget? child;
  final double intensity;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Stack(
      fit: StackFit.expand,
      children: [
        ColoredBox(color: scheme.surface),
        Positioned(
          top: -140,
          right: -100,
          child: _Blob(color: AppColors.brandBlue.withValues(alpha: 0.28 * intensity), size: 320),
        ),
        Positioned(
          top: 120,
          left: -160,
          child: _Blob(color: AppColors.brandViolet.withValues(alpha: 0.22 * intensity), size: 300),
        ),
        Positioned(
          bottom: -180,
          right: -80,
          child: _Blob(color: AppColors.brandPink.withValues(alpha: 0.14 * intensity), size: 340),
        ),
        if (child != null) child!,
      ],
    );
  }
}

class _Blob extends StatelessWidget {
  const _Blob({required this.color, required this.size});

  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color, color.withValues(alpha: 0)],
          ),
        ),
      ),
    );
  }
}
