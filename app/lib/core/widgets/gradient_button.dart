import 'package:flutter/material.dart';

import '../design/app_colors.dart';
import '../design/app_motion.dart';
import '../design/app_radius.dart';

/// The primary call-to-action: a bold gradient pill with a soft glow shadow
/// and a subtle press-scale micro-interaction. Large touch target (58dp).
class PrimaryButton extends StatefulWidget {
  const PrimaryButton({
    super.key,
    required this.label,
    this.icon,
    this.onPressed,
    this.expand = false,
    this.gradient,
  });

  final String label;
  final IconData? icon;
  final VoidCallback? onPressed;
  final bool expand;
  final Gradient? gradient;

  @override
  State<PrimaryButton> createState() => _PrimaryButtonState();
}

class _PrimaryButtonState extends State<PrimaryButton> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final disabled = widget.onPressed == null;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final gradient = widget.gradient ?? AppColors.heroGradientFor();
    final scheme = Theme.of(context).colorScheme;

    final scale = reduceMotion ? 1.0 : (_pressed ? 0.96 : 1.0);
    final child = AnimatedScale(
      scale: scale,
      duration: AppMotion.fast,
      curve: AppMotion.standard,
      child: Container(
        height: 58,
        padding: const EdgeInsets.symmetric(horizontal: 28),
        decoration: BoxDecoration(
          gradient: disabled ? null : gradient,
          color: disabled ? scheme.surfaceContainerHighest : null,
          borderRadius: AppRadius.pillR,
          boxShadow: disabled
              ? null
              : [
                  BoxShadow(
                    color: AppColors.brandViolet.withValues(alpha: 0.35),
                    blurRadius: 24,
                    offset: const Offset(0, 10),
                  ),
                ],
        ),
        child: Row(
          mainAxisSize: widget.expand ? MainAxisSize.max : MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (widget.icon != null) ...[
              Icon(widget.icon, color: disabled ? scheme.onSurfaceVariant : Colors.white, size: 20),
              const SizedBox(width: 10),
            ],
            Text(
              widget.label,
              style: TextStyle(
                color: disabled ? scheme.onSurfaceVariant : Colors.white,
                fontWeight: FontWeight.w700,
                fontSize: 16,
              ),
            ),
          ],
        ),
      ),
    );

    return GestureDetector(
      onTapDown: disabled || reduceMotion ? null : (_) => setState(() => _pressed = true),
      onTapUp: disabled || reduceMotion ? null : (_) => setState(() => _pressed = false),
      onTapCancel: disabled || reduceMotion ? null : () => setState(() => _pressed = false),
      onTap: widget.onPressed,
      child: widget.expand ? SizedBox(width: double.infinity, child: child) : child,
    );
  }
}

/// The secondary action: a glass pill, same footprint as [PrimaryButton],
/// with the same press-scale micro-interaction.
class GhostButton extends StatefulWidget {
  const GhostButton({super.key, required this.label, this.icon, this.onPressed, this.expand = false});

  final String label;
  final IconData? icon;
  final VoidCallback? onPressed;
  final bool expand;

  @override
  State<GhostButton> createState() => _GhostButtonState();
}

class _GhostButtonState extends State<GhostButton> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final disabled = widget.onPressed == null;
    final content = Container(
      height: 58,
      padding: const EdgeInsets.symmetric(horizontal: 24),
      // Only centre when we're deliberately filling the width. A Container
      // with `alignment` set and no width constraint EXPANDS to fill loose
      // constraints — which silently stretched every expand:false GhostButton
      // to full width (e.g. onboarding's "Skip" read as the primary action).
      alignment: widget.expand ? Alignment.center : null,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (widget.icon != null) ...[
            Icon(widget.icon, size: 20, color: scheme.onSurface),
            const SizedBox(width: 8),
          ],
          Text(widget.label, style: TextStyle(fontWeight: FontWeight.w700, color: scheme.onSurface)),
        ],
      ),
    );
    final material = Material(
      color: scheme.surfaceContainerHighest,
      shape: RoundedRectangleBorder(borderRadius: AppRadius.pillR, side: BorderSide(color: scheme.outlineVariant)),
      child: InkWell(
        borderRadius: AppRadius.pillR,
        onTapDown: disabled || reduceMotion ? null : (_) => setState(() => _pressed = true),
        onTapUp: disabled || reduceMotion ? null : (_) => setState(() => _pressed = false),
        onTapCancel: disabled || reduceMotion ? null : () => setState(() => _pressed = false),
        onTap: widget.onPressed,
        child: widget.expand ? SizedBox(width: double.infinity, child: content) : content,
      ),
    );
    return AnimatedScale(
      scale: reduceMotion ? 1.0 : (_pressed ? 0.96 : 1.0),
      duration: AppMotion.fast,
      curve: AppMotion.standard,
      child: material,
    );
  }
}

/// A round floating icon button — replaces bare `IconButton` in app bars and
/// toolbars. `filled: true` gives it the brand gradient treatment. Presses
/// scale down slightly, matching [PrimaryButton] and [GhostButton].
class IconPillButton extends StatefulWidget {
  const IconPillButton({
    super.key,
    required this.icon,
    this.onPressed,
    this.tooltip,
    this.filled = false,
  });

  final IconData icon;
  final VoidCallback? onPressed;
  final String? tooltip;
  final bool filled;

  @override
  State<IconPillButton> createState() => _IconPillButtonState();
}

class _IconPillButtonState extends State<IconPillButton> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final disabled = widget.onPressed == null;
    final material = Material(
      color: widget.filled ? null : scheme.surfaceContainerHighest,
      shape: const CircleBorder(),
      child: Ink(
        decoration:
            widget.filled ? BoxDecoration(gradient: AppColors.heroGradientFor(), shape: BoxShape.circle) : null,
        child: InkWell(
          customBorder: const CircleBorder(),
          onTapDown: disabled || reduceMotion ? null : (_) => setState(() => _pressed = true),
          onTapUp: disabled || reduceMotion ? null : (_) => setState(() => _pressed = false),
          onTapCancel: disabled || reduceMotion ? null : () => setState(() => _pressed = false),
          onTap: widget.onPressed,
          child: SizedBox(
            width: 48,
            height: 48,
            child: Icon(widget.icon, size: 22, color: widget.filled ? Colors.white : scheme.onSurface),
          ),
        ),
      ),
    );
    final button = AnimatedScale(
      scale: reduceMotion ? 1.0 : (_pressed ? 0.96 : 1.0),
      duration: AppMotion.fast,
      curve: AppMotion.standard,
      child: material,
    );
    if (widget.tooltip == null) return button;
    return Tooltip(message: widget.tooltip!, child: button);
  }
}
