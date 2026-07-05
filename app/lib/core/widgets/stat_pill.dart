import 'package:flutter/material.dart';

import '../design/app_radius.dart';
import '../design/app_spacing.dart';

/// A big-number stat inside hero surfaces ("31 min", "Coach 1") — an icon
/// badge, an overline label, and a bold value, floating in its own soft pill.
class StatPill extends StatelessWidget {
  const StatPill({super.key, required this.label, required this.value, this.icon, this.accent});

  final String label;
  final String value;
  final IconData? icon;
  final Color? accent;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final tint = accent ?? scheme.primary;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest.withValues(alpha: 0.6),
        borderRadius: AppRadius.lgR,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 18, color: tint),
            const SizedBox(width: AppSpacing.sm),
          ],
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 180),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(label.toUpperCase(), style: theme.textTheme.labelSmall),
                Text(value, style: theme.textTheme.titleLarge, maxLines: 2, overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
