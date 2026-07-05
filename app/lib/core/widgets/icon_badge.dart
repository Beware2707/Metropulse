import 'package:flutter/material.dart';

import '../design/app_radius.dart';

/// A soft, rounded, tinted (or gradient) container around an icon — the
/// app's icon system. Every icon that isn't purely decorative sits inside
/// one of these rather than floating bare against the background.
class IconBadge extends StatelessWidget {
  const IconBadge({
    super.key,
    required this.icon,
    this.size = 44,
    this.iconSize = 22,
    this.color,
    this.gradient,
    this.foreground,
  });

  final IconData icon;
  final double size;
  final double iconSize;
  final Color? color;
  final Gradient? gradient;
  final Color? foreground;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final bg = color ?? scheme.primary.withValues(alpha: 0.14);
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: gradient == null ? bg : null,
        gradient: gradient,
        borderRadius: AppRadius.mdR,
      ),
      alignment: Alignment.center,
      child: Icon(icon, size: iconSize, color: foreground ?? (gradient == null ? scheme.primary : Colors.white)),
    );
  }
}
