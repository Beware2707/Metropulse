import 'package:flutter/material.dart';

import '../design/app_radius.dart';
import '../design/app_spacing.dart';

/// A single borderless line of information — MetroPulse's alternative to
/// wrapping every fact in its own bordered card. Use this for sequential,
/// glanceable content (a commute status, a nearby station, a favourite);
/// reserve a bordered [GlassSurface] for content that's genuinely a
/// separable, floating object (the active-journey banner, a hero card).
///
/// Emotion → Decision → Action → Information: [title] is the decision-ready
/// fact ("Leave in 8 min"), [subtitle] is the supporting detail ("Home →
/// Office"), [trailing] is at most one more glanceable fact (a coach chip),
/// and a chevron only appears when there's somewhere to go for the rest.
class MomentRow extends StatelessWidget {
  const MomentRow({
    super.key,
    this.leading,
    required this.title,
    this.subtitle,
    this.trailing,
    this.onTap,
    this.dense = false,
  });

  final Widget? leading;
  final Widget title;
  final Widget? subtitle;
  final Widget? trailing;
  final VoidCallback? onTap;

  /// Tighter vertical rhythm for rows inside an already-compact list
  /// (e.g. stacked favourites) rather than the default breathing room.
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      borderRadius: AppRadius.mdR,
      child: Padding(
        padding: EdgeInsets.symmetric(
          vertical: dense ? AppSpacing.sm : AppSpacing.lg,
          horizontal: AppSpacing.xs,
        ),
        child: Row(
          children: [
            if (leading != null) ...[leading!, const SizedBox(width: AppSpacing.lg)],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  title,
                  if (subtitle != null) ...[const SizedBox(height: 3), subtitle!],
                ],
              ),
            ),
            if (trailing != null) ...[const SizedBox(width: AppSpacing.md), trailing!],
            if (onTap != null) ...[
              const SizedBox(width: AppSpacing.xs),
              Icon(Icons.chevron_right_rounded, color: scheme.onSurfaceVariant, size: 20),
            ],
          ],
        ),
      ),
    );
  }
}

/// A hairline between [MomentRow]s — barely there, organising the list
/// without ever competing with it for attention.
class MomentDivider extends StatelessWidget {
  const MomentDivider({super.key});

  @override
  Widget build(BuildContext context) {
    return Divider(
      height: AppSpacing.xs,
      thickness: 1,
      color: Theme.of(context).colorScheme.outlineVariant.withValues(alpha: 0.5),
    );
  }
}

/// A flowing group of [MomentRow]s separated by hairlines — no card, no
/// border around the whole group. Rows that would render nothing (a hidden
/// section with no data) simply aren't passed in; this widget doesn't know
/// or care why a row is absent.
class MomentList extends StatelessWidget {
  const MomentList({super.key, required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    if (children.isEmpty) return const SizedBox.shrink();
    return Column(
      children: [
        for (var i = 0; i < children.length; i++) ...[
          if (i > 0) const MomentDivider(),
          children[i],
        ],
      ],
    );
  }
}
