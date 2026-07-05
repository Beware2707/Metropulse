import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/favourites/favourites_screen.dart';
import '../features/history/journey_history_screen.dart';
import '../features/home/home_screen.dart';
import '../features/journey_mode/journey_mode_screen.dart';
import '../features/map/live_map_screen.dart';
import '../features/notifications/notifications_screen.dart';
import '../features/planner/journey_planner_screen.dart';
import '../features/search/search_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/splash/splash_screen.dart';
import '../features/station/station_detail_screen.dart';
import '../features/train/train_detail_screen.dart';
import 'root_shell.dart';

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/splash',
    routes: [
      GoRoute(path: '/splash', builder: (_, __) => const SplashScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) => RootShell(
          navigationShell: navigationShell,
          currentIndex: navigationShell.currentIndex,
          onTap: (index) => navigationShell.goBranch(
            index,
            initialLocation: index == navigationShell.currentIndex,
          ),
        ),
        branches: [
          StatefulShellBranch(routes: [GoRoute(path: '/', builder: (_, __) => const HomeScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/map', builder: (_, __) => const LiveMapScreen())]),
          StatefulShellBranch(
              routes: [GoRoute(path: '/favourites', builder: (_, __) => const FavouritesScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/settings', builder: (_, __) => const SettingsScreen())]),
        ],
      ),
      GoRoute(
        path: '/station/:stopId',
        builder: (_, state) =>
            StationDetailScreen(stopId: state.pathParameters['stopId']!),
      ),
      GoRoute(
        path: '/train/:vehicleId',
        builder: (_, state) =>
            TrainDetailScreen(vehicleId: state.pathParameters['vehicleId']!),
      ),
      GoRoute(
        path: '/planner',
        builder: (_, state) => JourneyPlannerScreen(
          initialOriginId: state.uri.queryParameters['origin'],
          initialDestinationId: state.uri.queryParameters['destination'],
        ),
      ),
      GoRoute(path: '/journey', builder: (_, __) => const JourneyModeScreen()),
      GoRoute(path: '/search', builder: (_, __) => const SearchScreen()),
      GoRoute(path: '/journeys/history', builder: (_, __) => const JourneyHistoryScreen()),
      GoRoute(path: '/notifications', builder: (_, __) => const NotificationsScreen()),
    ],
  );
});
