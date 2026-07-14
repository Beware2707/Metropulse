import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'design/app_spacing.dart';
import 'l10n_ext.dart';
import 'widgets/floating_nav_bar.dart';
import 'widgets/gradient_button.dart';
import 'widgets/settle_fade_in.dart';

/// The currently visible shell tab (0 = Home, 1 = Journey, 2 = Explore, 3 =
/// You), kept in sync by [RootShell]. Exists so a tab's own screen can tell
/// whether it's actually on screen right now — the shell keeps every
/// branch's widget tree alive via `IndexedStack`, so a plain
/// `didChangeAppLifecycleState` only catches the app backgrounding
/// entirely, not the user simply switching to a different tab.
final activeShellTabIndexProvider = StateProvider<int>((ref) => 0);

/// go_router's `StatefulShellRoute` wraps the four hero tabs — Home
/// (everything starts here), Journey (the current or planned trip), Explore
/// (stations, map, places), You (favourites, history/Replay, settings) — in
/// this shell, which lays the floating glass nav bar over each tab's own
/// Scaffold, plus a global floating mic (Voice is deliberately not a tab —
/// it should be reachable from anywhere, the way it's used: a quick
/// question, not a destination). Task flows (Search, Planner, Station/Train
/// detail, ...) are pushed as ordinary full-screen routes on the root
/// navigator and cover this shell entirely.
class RootShell extends ConsumerStatefulWidget {
  const RootShell({super.key, required this.navigationShell, required this.onTap, required this.currentIndex});

  final Widget navigationShell;
  final ValueChanged<int> onTap;
  final int currentIndex;

  /// The tab icons, in shell order. Labels are localised per-build from
  /// [BuildContext.t] (see [_localizedDestinations]) so switching language
  /// re-labels the nav bar without any icon duplication here.
  static const _iconSpecs = [
    (Icons.home_outlined, Icons.home_rounded),
    (Icons.directions_subway_outlined, Icons.directions_subway_filled_rounded),
    (Icons.explore_outlined, Icons.explore_rounded),
    (Icons.person_outline_rounded, Icons.person_rounded),
  ];

  static List<NavDestinationSpec> _localizedDestinations(BuildContext context) {
    final t = context.t;
    final labels = [t.navHome, t.navJourney, t.navExplore, t.navYou];
    return [
      for (var i = 0; i < _iconSpecs.length; i++)
        NavDestinationSpec(
          icon: _iconSpecs[i].$1,
          activeIcon: _iconSpecs[i].$2,
          label: labels[i],
        ),
    ];
  }

  @override
  ConsumerState<RootShell> createState() => _RootShellState();
}

class _RootShellState extends ConsumerState<RootShell> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncActiveTab());
  }

  @override
  void didUpdateWidget(covariant RootShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.currentIndex != widget.currentIndex) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _syncActiveTab());
    }
  }

  void _syncActiveTab() {
    if (!mounted) return;
    ref.read(activeShellTabIndexProvider.notifier).state = widget.currentIndex;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBody: true,
      body: Stack(
        children: [
          widget.navigationShell,
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
        destinations: RootShell._localizedDestinations(context),
        currentIndex: widget.currentIndex,
        onTap: widget.onTap,
      ),
    );
  }
}
