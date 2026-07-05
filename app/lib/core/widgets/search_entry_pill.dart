import 'package:flutter/material.dart';

import '../design/app_radius.dart';
import '../design/app_spacing.dart';
import 'glass_surface.dart';

/// A tappable, animated search entry — the Home-screen doorway into Search.
/// Not a real text field: it always navigates to the full Search screen,
/// matching how Instagram/Spotify treat their home search bars.
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
        scale: _pressed ? 0.98 : 1.0,
        duration: const Duration(milliseconds: 120),
        child: GlassSurface(
          borderRadius: AppRadius.pillR,
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl, vertical: AppSpacing.lg),
          child: Row(
            children: [
              Icon(Icons.search_rounded, color: scheme.onSurfaceVariant),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text(widget.hint,
                    style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 15, fontWeight: FontWeight.w500)),
              ),
              Icon(Icons.mic_none_rounded, size: 20, color: scheme.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }
}
