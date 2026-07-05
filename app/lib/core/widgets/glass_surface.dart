import 'dart:ui';

import 'package:flutter/material.dart';

import '../design/app_radius.dart';

/// A floating, softly rounded surface — the design system's replacement for
/// `Card` everywhere. `blur: true` gives true glassmorphism (BackdropFilter);
/// leave it false for opaque rows in long lists, where blur is wasted GPU
/// work and hurts scroll performance.
class GlassSurface extends StatelessWidget {
  const GlassSurface({
    super.key,
    required this.child,
    this.padding,
    this.borderRadius,
    this.blur = false,
    this.gradient,
    this.color,
    this.border = true,
    this.onTap,
  });

  final Widget child;
  final EdgeInsetsGeometry? padding;
  final BorderRadius? borderRadius;
  final bool blur;
  final Gradient? gradient;
  final Color? color;
  final bool border;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final radius = borderRadius ?? AppRadius.xlR;
    final resolvedColor = color ?? scheme.surfaceContainerHighest;

    final decorated = DecoratedBox(
      decoration: BoxDecoration(
        color: gradient == null ? resolvedColor.withValues(alpha: blur ? 0.62 : 1) : null,
        gradient: gradient,
        borderRadius: radius,
        border: border ? Border.all(color: scheme.outlineVariant, width: 1) : null,
      ),
      child: ClipRRect(
        borderRadius: radius,
        child: Material(
          type: MaterialType.transparency,
          child: InkWell(
            onTap: onTap,
            child: Padding(padding: padding ?? const EdgeInsets.all(20), child: child),
          ),
        ),
      ),
    );

    if (!blur) return decorated;
    return ClipRRect(
      borderRadius: radius,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
        child: decorated,
      ),
    );
  }
}
