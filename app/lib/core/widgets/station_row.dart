import 'package:flutter/material.dart';

import '../../domain/models/station.dart';
import '../design/app_colors.dart';
import '../design/app_spacing.dart';
import 'glass_surface.dart';
import 'icon_badge.dart';

/// A single tappable station result — shared between the full-screen Search
/// takeover and the in-sheet station picker so both stay visually identical.
class StationRow extends StatelessWidget {
  const StationRow({
    super.key,
    required this.station,
    required this.icon,
    required this.onTap,
    this.subtitle,
    this.subtitleIcon,
    this.dimmed = false,
  });

  final Station station;
  final IconData icon;
  final void Function(Station) onTap;

  /// An optional caption beneath the station name — "Also known as…" for an
  /// alias match, "Near…" for a landmark match.
  final String? subtitle;

  /// A small icon shown before [subtitle] (e.g. a near-me pin for a
  /// landmark match) — ignored when [subtitle] is null.
  final IconData? subtitleIcon;

  /// Slightly de-emphasises the title — used for weaker (landmark-only)
  /// matches so a daily commuter's exact-name hits still read as primary.
  final bool dimmed;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: GlassSurface(
        onTap: () => onTap(station),
        child: Row(
          children: [
            IconBadge(icon: icon, color: AppColors.brandBlue.withValues(alpha: 0.14), foreground: AppColors.brandBlue),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    station.name,
                    style: theme.textTheme.titleMedium?.copyWith(color: dimmed ? theme.colorScheme.onSurface.withValues(alpha: 0.72) : null),
                  ),
                  if (subtitle != null) ...[
                    const SizedBox(height: 2),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (subtitleIcon != null) ...[
                          Icon(subtitleIcon, size: 14, color: theme.colorScheme.onSurfaceVariant),
                          const SizedBox(width: 4),
                        ],
                        Flexible(child: Text(subtitle!, style: theme.textTheme.bodySmall)),
                      ],
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A small uppercase group label above a cluster of search results (e.g.
/// "FAVOURITES", "RECENT") — distinct from [SectionHeader], which is a
/// larger heading with an optional trailing action used on full screens.
class SearchSectionLabel extends StatelessWidget {
  const SearchSectionLabel(this.text, {super.key, this.topSpacing = AppSpacing.md});

  final String text;
  final double topSpacing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(4, topSpacing, 4, AppSpacing.sm),
      child: Text(text.toUpperCase(), style: Theme.of(context).textTheme.labelSmall),
    );
  }
}
