import 'package:flutter/material.dart';

import 'widgets/floating_nav_bar.dart';

/// go_router's `StatefulShellRoute` wraps the four top-level tabs (Home, Map,
/// Favourites, Settings) in this shell, which lays the floating glass nav
/// bar over each tab's own Scaffold. Task flows (Search, Planner, Journey
/// Mode, Station/Train detail, ...) are pushed as ordinary full-screen
/// routes on the root navigator and cover the nav bar entirely.
class RootShell extends StatelessWidget {
  const RootShell({super.key, required this.navigationShell, required this.onTap, required this.currentIndex});

  final Widget navigationShell;
  final ValueChanged<int> onTap;
  final int currentIndex;

  static const destinations = [
    NavDestinationSpec(icon: Icons.home_outlined, activeIcon: Icons.home_rounded, label: 'Home'),
    NavDestinationSpec(icon: Icons.map_outlined, activeIcon: Icons.map_rounded, label: 'Map'),
    NavDestinationSpec(icon: Icons.star_outline_rounded, activeIcon: Icons.star_rounded, label: 'Saved'),
    NavDestinationSpec(icon: Icons.settings_outlined, activeIcon: Icons.settings_rounded, label: 'Settings'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBody: true,
      body: navigationShell,
      bottomNavigationBar: FloatingNavBar(
        destinations: destinations,
        currentIndex: currentIndex,
        onTap: onTap,
      ),
    );
  }
}
