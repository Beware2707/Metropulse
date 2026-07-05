import 'package:flutter/material.dart';

import '../design/app_radius.dart';

/// A moving shimmer-sweep placeholder shown while a section loads — the
/// premium alternative to a flat opacity pulse. Honours reduced-motion by
/// freezing at mid-opacity.
class ShimmerBlock extends StatefulWidget {
  const ShimmerBlock({super.key, this.height = 72, this.width, this.radius});

  final double height;
  final double? width;
  final double? radius;

  @override
  State<ShimmerBlock> createState() => _ShimmerBlockState();
}

class _ShimmerBlockState extends State<ShimmerBlock> with SingleTickerProviderStateMixin {
  late final AnimationController _controller =
      AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final base = scheme.surfaceContainerHighest;
    final highlight = scheme.onSurface.withValues(alpha: 0.06);
    final radius = BorderRadius.circular(widget.radius ?? AppRadius.lg);
    final reduceMotion = MediaQuery.of(context).disableAnimations;

    final block = ClipRRect(
      borderRadius: radius,
      child: SizedBox(
        height: widget.height,
        width: widget.width,
        child: ColoredBox(color: base),
      ),
    );

    if (reduceMotion) {
      return Opacity(
        opacity: 0.7,
        child: block,
      );
    }

    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        return ClipRRect(
          borderRadius: radius,
          child: SizedBox(
            height: widget.height,
            width: widget.width,
            child: ShaderMask(
              blendMode: BlendMode.srcATop,
              shaderCallback: (rect) {
                final dx = _controller.value * 2 - 0.5;
                return LinearGradient(
                  begin: Alignment(-1.5 + dx * 3, 0),
                  end: Alignment(0 + dx * 3, 0),
                  colors: [base, highlight, base],
                  stops: const [0.35, 0.5, 0.65],
                ).createShader(rect);
              },
              child: ColoredBox(color: base),
            ),
          ),
        );
      },
    );
  }
}
