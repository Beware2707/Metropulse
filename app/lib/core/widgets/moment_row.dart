import 'package:flutter/material.dart';

import '../design/app_motion.dart';
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
///
/// Tappable rows press-scale on touch, the same feedback every button in the
/// app already gives — untappable rows (no [onTap]) never do.
class MomentRow extends StatefulWidget {
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
  State<MomentRow> createState() => _MomentRowState();
}

class _MomentRowState extends State<MomentRow> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final tappable = widget.onTap != null;
    final content = InkWell(
      onTapDown: !tappable || reduceMotion ? null : (_) => setState(() => _pressed = true),
      onTapUp: !tappable || reduceMotion ? null : (_) => setState(() => _pressed = false),
      onTapCancel: !tappable || reduceMotion ? null : () => setState(() => _pressed = false),
      onTap: widget.onTap,
      borderRadius: AppRadius.mdR,
      child: Padding(
        padding: EdgeInsets.symmetric(
          vertical: widget.dense ? AppSpacing.sm : AppSpacing.lg,
          horizontal: AppSpacing.xs,
        ),
        child: Row(
          children: [
            if (widget.leading != null) ...[widget.leading!, const SizedBox(width: AppSpacing.lg)],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  widget.title,
                  if (widget.subtitle != null) ...[const SizedBox(height: 3), widget.subtitle!],
                ],
              ),
            ),
            if (widget.trailing != null) ...[const SizedBox(width: AppSpacing.md), widget.trailing!],
            if (tappable) ...[
              const SizedBox(width: AppSpacing.xs),
              Icon(Icons.chevron_right_rounded, color: scheme.onSurfaceVariant, size: 20),
            ],
          ],
        ),
      ),
    );
    if (!tappable || reduceMotion) return content;
    return AnimatedScale(
      scale: _pressed ? 0.98 : 1.0,
      duration: AppMotion.fast,
      curve: AppMotion.standard,
      child: content,
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
