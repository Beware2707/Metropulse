import 'package:flutter/material.dart';

import '../design/app_radius.dart';
import '../design/app_spacing.dart';
import 'glass_surface.dart';

/// Shared Hero tag between Home's search entry and the full-screen Search
/// takeover, so tapping it grows into the destination field instead of a
/// plain push — the "everything else disappears" Uber-style transition.
const kSearchHeroTag = 'app-search-field';

/// A huge, tappable search entry — the Home-screen doorway into Search. Not
/// a real text field: it always navigates to the full Search screen via a
/// Hero-animated takeover, matching how Uber/Instagram treat home search.
class SearchEntryPill extends StatefulWidget {
  const SearchEntryPill({super.key, required this.hint, required this.onTap});

  final String hint;
  final VoidCallback onTap;

  @override
  State<SearchEntryPill> createState() => _SearchEntryPillState();
}

class _SearchEntryPillState extends State<SearchEntryPill> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return GestureDetector(
      onTapDown: (_) => setState(() => _pressed = true),
      onTapUp: (_) => setState(() => _pressed = false),
      onTapCancel: () => setState(() => _pressed = false),
      onTap: widget.onTap,
      child: AnimatedScale(
        scale: _pressed ? 0.97 : 1.0,
        duration: const Duration(milliseconds: 120),
        curve: Curves.easeOut,
        child: Hero(
          tag: kSearchHeroTag,
          child: Material(
            type: MaterialType.transparency,
            child: GlassSurface(
              borderRadius: AppRadius.pillR,
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xxl, vertical: AppSpacing.xl),
              child: Row(
                children: [
                  Icon(Icons.search_rounded, color: scheme.onSurfaceVariant, size: 26),
                  const SizedBox(width: AppSpacing.lg),
                  Expanded(
                    child: Text(widget.hint,
                        style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 17, fontWeight: FontWeight.w600)),
                  ),
                  Icon(Icons.mic_none_rounded, size: 22, color: scheme.onSurfaceVariant),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
