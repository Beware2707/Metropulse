import 'package:flutter/material.dart';

import '../design/app_motion.dart';
import '../design/app_radius.dart';
import '../design/app_spacing.dart';
import 'glass_surface.dart';

/// Shared Hero tag between Home's search entry and the full-screen Search
/// takeover, so tapping it grows into the destination field instead of a
/// plain push — the "everything else disappears" Uber-style transition.
const kSearchHeroTag = 'app-search-field';

/// The single doorway into Search — deliberately the largest, boldest
/// element on Home, never sharing visual weight with anything else on the
/// screen. Not a real text field: it always navigates to the full Search
/// screen via a Hero-animated takeover, matching how Uber/Instagram treat
/// home search.
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
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final content = Hero(
      tag: kSearchHeroTag,
      child: Material(
        type: MaterialType.transparency,
        child: GlassSurface(
          borderRadius: AppRadius.xxlR,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xxl, vertical: AppSpacing.xxl),
          child: Row(
            children: [
              Icon(Icons.search_rounded, color: scheme.onSurfaceVariant, size: 28),
              const SizedBox(width: AppSpacing.lg),
              Expanded(
                child: Text(widget.hint,
                    style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 20, fontWeight: FontWeight.w700)),
              ),
              Icon(Icons.mic_none_rounded, size: 24, color: scheme.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );

    return GestureDetector(
      onTapDown: reduceMotion ? null : (_) => setState(() => _pressed = true),
      onTapUp: reduceMotion ? null : (_) => setState(() => _pressed = false),
      onTapCancel: reduceMotion ? null : () => setState(() => _pressed = false),
      onTap: widget.onTap,
      child: reduceMotion
          ? content
          : AnimatedScale(
              scale: _pressed ? 0.97 : 1.0,
              duration: AppMotion.fast,
              curve: AppMotion.standard,
              child: content,
            ),
    );
  }
}
