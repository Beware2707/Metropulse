import 'package:flutter/material.dart';

import '../design/app_colors.dart';
import '../design/app_spacing.dart';
import 'glass_surface.dart';
import 'gradient_button.dart';

/// A friendly, illustration-like empty/error state: a soft glowing gradient
/// medallion, a headline, and an optional action — replaces bare
/// "Couldn't load this section." list tiles everywhere. Centred and vertical
/// by default (the illustrated look); `compact: true` gives a slim inline
/// row for tight spaces.
class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.icon,
    required this.message,
    this.actionLabel,
    this.onAction,
    this.tint,
    this.compact = false,
  });

  final IconData icon;
  final String message;
  final String? actionLabel;
  final VoidCallback? onAction;
  final Color? tint;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final gradientColors = tint == null ? AppColors.heroGradient : [tint!, tint!.withValues(alpha: 0.6)];

    if (compact) {
      return GlassSurface(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Row(
          children: [
            _Medallion(gradientColors: gradientColors, icon: icon, size: 40, iconSize: 20),
            const SizedBox(width: AppSpacing.lg),
            Expanded(child: Text(message, style: theme.textTheme.bodyMedium)),
          ],
        ),
      );
    }

    return GlassSurface(
      padding: const EdgeInsets.all(AppSpacing.xxl),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _Medallion(gradientColors: gradientColors, icon: icon, size: 64, iconSize: 30),
          const SizedBox(height: AppSpacing.lg),
          Text(message, textAlign: TextAlign.center, style: theme.textTheme.bodyLarge),
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(height: AppSpacing.lg),
            GhostButton(label: actionLabel!, onPressed: onAction),
          ],
        ],
      ),
    );
  }
}

class _Medallion extends StatelessWidget {
  const _Medallion({required this.gradientColors, required this.icon, required this.size, required this.iconSize});

  final List<Color> gradientColors;
  final IconData icon;
  final double size;
  final double iconSize;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size + 28,
      height: size + 28,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              gradient: RadialGradient(
                colors: [gradientColors.first.withValues(alpha: 0.28), gradientColors.first.withValues(alpha: 0)],
              ),
            ),
          ),
          Container(
            width: size,
            height: size,
            decoration: BoxDecoration(gradient: LinearGradient(colors: gradientColors), shape: BoxShape.circle),
            alignment: Alignment.center,
            child: Icon(icon, color: Colors.white, size: iconSize),
          ),
        ],
      ),
    );
  }
}
