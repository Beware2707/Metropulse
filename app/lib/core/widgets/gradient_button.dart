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
    final gradient = widget.gradient ?? AppColors.heroGradientFor();
    final scheme = Theme.of(context).colorScheme;

    final child = AnimatedScale(
      scale: _pressed ? 0.96 : 1.0,
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
      onTapDown: disabled ? null : (_) => setState(() => _pressed = true),
      onTapUp: disabled ? null : (_) => setState(() => _pressed = false),
      onTapCancel: disabled ? null : () => setState(() => _pressed = false),
      onTap: widget.onPressed,
      child: widget.expand ? SizedBox(width: double.infinity, child: child) : child,
    );
  }
}

/// The secondary action: a glass pill, same footprint as [PrimaryButton].
class GhostButton extends StatelessWidget {
  const GhostButton({super.key, required this.label, this.icon, this.onPressed, this.expand = false});

  final String label;
  final IconData? icon;
  final VoidCallback? onPressed;
  final bool expand;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final content = Container(
      height: 58,
      padding: const EdgeInsets.symmetric(horizontal: 24),
      alignment: Alignment.center,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: 20, color: scheme.onSurface), const SizedBox(width: 8)],
          Text(label, style: TextStyle(fontWeight: FontWeight.w700, color: scheme.onSurface)),
        ],
      ),
    );
    return Material(
      color: scheme.surfaceContainerHighest,
      shape: RoundedRectangleBorder(borderRadius: AppRadius.pillR, side: BorderSide(color: scheme.outlineVariant)),
      child: InkWell(
        borderRadius: AppRadius.pillR,
        onTap: onPressed,
        child: expand ? SizedBox(width: double.infinity, child: content) : content,
      ),
    );
  }
}

/// A round floating icon button — replaces bare `IconButton` in app bars and
/// toolbars. `filled: true` gives it the brand gradient treatment.
class IconPillButton extends StatelessWidget {
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
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final button = Material(
      color: filled ? null : scheme.surfaceContainerHighest,
      shape: const CircleBorder(),
      child: Ink(
        decoration:
            filled ? BoxDecoration(gradient: AppColors.heroGradientFor(), shape: BoxShape.circle) : null,
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: onPressed,
          child: SizedBox(
            width: 48,
            height: 48,
            child: Icon(icon, size: 22, color: filled ? Colors.white : scheme.onSurface),
          ),
        ),
      ),
    );
    if (tooltip == null) return button;
    return Tooltip(message: tooltip!, child: button);
  }
}
