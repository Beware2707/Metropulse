import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/favourites/favourites_screen.dart';
import '../features/home/home_screen.dart';
import '../features/journey_mode/journey_mode_screen.dart';
import '../features/map/live_map_screen.dart';
import '../features/planner/journey_planner_screen.dart';
import '../features/search/search_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/splash/splash_screen.dart';
import '../features/station/station_detail_screen.dart';
import '../features/train/train_detail_screen.dart';

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/splash',
    routes: [
      GoRoute(path: '/splash', builder: (_, __) => const SplashScreen()),
      GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
      GoRoute(path: '/map', builder: (_, __) => const LiveMapScreen()),
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
      GoRoute(path: '/planner', builder: (_, __) => const JourneyPlannerScreen()),
      GoRoute(path: '/journey', builder: (_, __) => const JourneyModeScreen()),
      GoRoute(path: '/search', builder: (_, __) => const SearchScreen()),
      GoRoute(path: '/favourites', builder: (_, __) => const FavouritesScreen()),
      GoRoute(path: '/settings', builder: (_, __) => const SettingsScreen()),
    ],
  );
});
