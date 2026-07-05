import 'package:flutter/material.dart';

import '../../domain/models/station.dart';
import '../design/app_colors.dart';
import '../design/app_spacing.dart';
import 'glass_surface.dart';
import 'icon_badge.dart';

/// A single tappable station result — shared between the full-screen Search
/// takeover and the in-sheet station picker so both stay visually identical.
class StationRow extends StatelessWidget {
  const StationRow({super.key, required this.station, required this.icon, required this.onTap});

  final Station station;
  final IconData icon;
  final void Function(Station) onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: GlassSurface(
        onTap: () => onTap(station),
        child: Row(
          children: [
            IconBadge(icon: icon, color: AppColors.brandBlue.withValues(alpha: 0.14), foreground: AppColors.brandBlue),
            const SizedBox(width: AppSpacing.md),
            Expanded(child: Text(station.name, style: Theme.of(context).textTheme.titleMedium)),
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
