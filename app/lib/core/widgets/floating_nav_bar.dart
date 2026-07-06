import 'dart:ui';

import 'package:flutter/material.dart';

import '../design/app_colors.dart';
import '../design/app_motion.dart';
import '../design/app_radius.dart';

class NavDestinationSpec {
  const NavDestinationSpec({required this.icon, required this.activeIcon, required this.label});

  final IconData icon;
  final IconData activeIcon;
  final String label;
}

/// The app's floating bottom navigation — a glass pill hovering over
/// content, replacing the flat Material `NavigationBar`.
class FloatingNavBar extends StatelessWidget {
  const FloatingNavBar({super.key, required this.destinations, required this.currentIndex, required this.onTap});

  final List<NavDestinationSpec> destinations;
  final int currentIndex;
  final ValueChanged<int> onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SafeArea(
      minimum: const EdgeInsets.fromLTRB(20, 0, 20, 16),
      child: ClipRRect(
        borderRadius: AppRadius.pillR,
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30),
          child: Container(
            height: 68,
            padding: const EdgeInsets.symmetric(horizontal: 8),
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHighest.withValues(alpha: 0.82),
              borderRadius: AppRadius.pillR,
              border: Border.all(color: scheme.outlineVariant),
              boxShadow: [
                BoxShadow(color: Colors.black.withValues(alpha: 0.28), blurRadius: 30, offset: const Offset(0, 14)),
              ],
            ),
            child: Row(
              children: [
                for (var i = 0; i < destinations.length; i++)
                  Expanded(
                    child: _NavItem(
                      spec: destinations[i],
                      selected: i == currentIndex,
                      onTap: () => onTap(i),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  const _NavItem({required this.spec, required this.selected, required this.onTap});

  final NavDestinationSpec spec;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: AnimatedContainer(
        duration: reduceMotion ? Duration.zero : AppMotion.medium,
        curve: AppMotion.standard,
        margin: const EdgeInsets.symmetric(vertical: 10, horizontal: 4),
        decoration: BoxDecoration(
          gradient: selected ? AppColors.heroGradientFor() : null,
          borderRadius: AppRadius.pillR,
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(selected ? spec.activeIcon : spec.icon,
                size: 22, color: selected ? Colors.white : scheme.onSurfaceVariant),
            const SizedBox(height: 3),
            AnimatedDefaultTextStyle(
              duration: reduceMotion ? Duration.zero : AppMotion.medium,
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w700,
                color: selected ? Colors.white : scheme.onSurfaceVariant,
              ),
              child: Text(spec.label),
            ),
          ],
        ),
      ),
    );
  }
}
