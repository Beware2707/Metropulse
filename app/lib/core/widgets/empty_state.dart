import 'package:flutter/material.dart';

import '../design/app_colors.dart';
import '../design/app_radius.dart';
import '../design/app_spacing.dart';
import 'glass_surface.dart';
import 'gradient_button.dart';

/// A friendly, illustration-like empty/error state: a soft gradient icon
/// medallion, a headline, a short body, and an optional action — replaces
/// bare "Couldn't load this section." list tiles everywhere.
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
    final gradientColors = tint == null
        ? AppColors.heroGradient
        : [tint!, tint!.withValues(alpha: 0.6)];
    return GlassSurface(
      padding: EdgeInsets.all(compact ? AppSpacing.lg : AppSpacing.xxl),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: compact ? 40 : 52,
                height: compact ? 40 : 52,
                decoration: BoxDecoration(
                  gradient: LinearGradient(colors: gradientColors),
                  borderRadius: AppRadius.mdR,
                ),
                alignment: Alignment.center,
                child: Icon(icon, color: Colors.white, size: compact ? 20 : 26),
              ),
              const SizedBox(width: AppSpacing.lg),
              Expanded(
                child: Text(message, style: compact ? theme.textTheme.bodyMedium : theme.textTheme.bodyLarge),
              ),
            ],
          ),
          if (actionLabel != null && onAction != null) ...[
            const SizedBox(height: AppSpacing.lg),
            GhostButton(label: actionLabel!, onPressed: onAction),
          ],
        ],
      ),
    );
  }
}
