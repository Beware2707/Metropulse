import 'dart:ui';

import 'package:flutter/material.dart';

import '../design/app_motion.dart';
import '../design/app_radius.dart';

/// A floating, softly rounded surface — the design system's replacement for
/// `Card` everywhere. `blur: true` gives true glassmorphism (BackdropFilter);
/// leave it false for opaque rows in long lists, where blur is wasted GPU
/// work and hurts scroll performance. Tappable surfaces press-scale on
/// touch, the same feedback every button in the app already gives.
class GlassSurface extends StatefulWidget {
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
  State<GlassSurface> createState() => _GlassSurfaceState();
}

class _GlassSurfaceState extends State<GlassSurface> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final tappable = widget.onTap != null;
    final radius = widget.borderRadius ?? AppRadius.xlR;
    final resolvedColor = widget.color ?? scheme.surfaceContainerHighest;

    final decorated = DecoratedBox(
      decoration: BoxDecoration(
        color: widget.gradient == null ? resolvedColor.withValues(alpha: widget.blur ? 0.62 : 1) : null,
        gradient: widget.gradient,
        borderRadius: radius,
        border: widget.border ? Border.all(color: scheme.outlineVariant, width: 1) : null,
      ),
      child: ClipRRect(
        borderRadius: radius,
        child: Material(
          type: MaterialType.transparency,
          child: InkWell(
            onTapDown: !tappable || reduceMotion ? null : (_) => setState(() => _pressed = true),
            onTapUp: !tappable || reduceMotion ? null : (_) => setState(() => _pressed = false),
            onTapCancel: !tappable || reduceMotion ? null : () => setState(() => _pressed = false),
            onTap: widget.onTap,
            child: Padding(padding: widget.padding ?? const EdgeInsets.all(20), child: widget.child),
          ),
        ),
      ),
    );

    final blurred = !widget.blur
        ? decorated
        : ClipRRect(
            borderRadius: radius,
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
              child: decorated,
            ),
          );

    if (!tappable || reduceMotion) return blurred;
    return AnimatedScale(
      scale: _pressed ? 0.98 : 1.0,
      duration: AppMotion.fast,
      curve: AppMotion.standard,
      child: blurred,
    );
  }
}
