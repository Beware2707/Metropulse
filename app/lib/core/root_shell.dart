import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import 'design/app_spacing.dart';
import 'widgets/floating_nav_bar.dart';
import 'widgets/gradient_button.dart';
import 'widgets/settle_fade_in.dart';

/// go_router's `StatefulShellRoute` wraps the four hero tabs — Home
/// (everything starts here), Journey (the current or planned trip), Explore
/// (stations, map, places), You (favourites, history/Replay, settings) — in
/// this shell, which lays the floating glass nav bar over each tab's own
/// Scaffold, plus a global floating mic (Voice is deliberately not a tab —
/// it should be reachable from anywhere, the way it's used: a quick
/// question, not a destination). Task flows (Search, Planner, Station/Train
/// detail, ...) are pushed as ordinary full-screen routes on the root
/// navigator and cover this shell entirely.
class RootShell extends StatelessWidget {
  const RootShell({super.key, required this.navigationShell, required this.onTap, required this.currentIndex});

  final Widget navigationShell;
  final ValueChanged<int> onTap;
  final int currentIndex;

  static const destinations = [
    NavDestinationSpec(icon: Icons.home_outlined, activeIcon: Icons.home_rounded, label: 'Home'),
    NavDestinationSpec(
        icon: Icons.directions_subway_outlined, activeIcon: Icons.directions_subway_filled_rounded, label: 'Journey'),
    NavDestinationSpec(icon: Icons.explore_outlined, activeIcon: Icons.explore_rounded, label: 'Explore'),
    NavDestinationSpec(icon: Icons.person_outline_rounded, activeIcon: Icons.person_rounded, label: 'You'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBody: true,
      body: Stack(
        children: [
          navigationShell,
          Positioned(
            left: AppSpacing.lg,
            bottom: 108,
            child: SettleFadeIn(
              child: IconPillButton(
                icon: Icons.mic_none_rounded,
                tooltip: 'Metro Assistant',
                filled: true,
                onPressed: () => context.push('/assistant'),
              ),
            ),
          ),
        ],
      ),
      bottomNavigationBar: FloatingNavBar(
        destinations: destinations,
        currentIndex: currentIndex,
        onTap: onTap,
      ),
    );
  }
}
