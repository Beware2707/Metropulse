import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'config.dart';
import '../features/favourites/favourites_screen.dart';
import '../features/history/journey_history_screen.dart';
import '../features/help/help_screen.dart';
import '../features/home/home_screen.dart';
import '../features/journey_mode/journey_mode_screen.dart';
import '../features/legal/legal_content.dart';
import '../features/legal/legal_doc_screen.dart';
import '../features/map/live_map_screen.dart';
import '../features/meet/meet_screen.dart';
import '../features/disruptions/disruptions_screen.dart';
import '../features/network_map/network_map_screen.dart';
import '../features/notifications/notifications_screen.dart';
import '../features/onboarding/onboarding_screen.dart';
import '../features/park_and_ride/park_and_ride_screen.dart';
import '../features/planner/journey_planner_screen.dart';
import '../features/search/search_screen.dart';
import '../features/settings/settings_screen.dart';
import '../features/splash/splash_screen.dart';
import '../features/station/station_detail_screen.dart';
import '../features/tickets/tickets_screen.dart';
import '../features/train/train_detail_screen.dart';
import '../features/voice/voice_assistant_screen.dart';
import '../features/you/you_screen.dart';
import 'root_shell.dart';

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/splash',
    routes: [
      GoRoute(path: '/splash', builder: (_, __) => const SplashScreen()),
      GoRoute(path: '/onboarding', builder: (_, __) => const OnboardingScreen()),
      // Four hero tabs: Home (everything starts here), Journey (the current
      // or planned trip — Metro Companion), Explore (stations, map,
      // places), You (favourites, history/Replay, notifications, settings).
      // Voice is deliberately not a tab — it's a global floating action (see
      // RootShell) available from any of the four.
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
          StatefulShellBranch(routes: [GoRoute(path: '/journey', builder: (_, __) => const JourneyModeScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/explore', builder: (_, __) => const LiveMapScreen())]),
          StatefulShellBranch(routes: [GoRoute(path: '/you', builder: (_, __) => const YouScreen())]),
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
      GoRoute(
        path: '/park-and-ride',
        builder: (_, state) => ParkAndRideScreen(
          initialDestinationId: state.uri.queryParameters['destination'],
        ),
      ),
      GoRoute(path: '/meet-up', builder: (_, __) => const MeetScreen()),
      GoRoute(
        path: '/network-map',
        builder: (_, state) => NetworkMapScreen(
          initialOriginId: state.uri.queryParameters['origin'],
          initialDestinationId: state.uri.queryParameters['destination'],
        ),
      ),
      GoRoute(
        path: '/search',
        builder: (_, state) => SearchScreen(
          mapPickerMode: state.uri.queryParameters['mapPicker'] == 'true',
        ),
      ),
      GoRoute(path: '/favourites', builder: (_, __) => const FavouritesScreen()),
      GoRoute(path: '/tickets', builder: (_, __) => const TicketsScreen()),
      GoRoute(path: '/help', builder: (_, __) => const HelpScreen()),
      GoRoute(path: '/settings', builder: (_, __) => const SettingsScreen()),
      GoRoute(
        path: '/privacy-policy',
        builder: (_, __) => const LegalDocScreen(title: 'Privacy Policy', blocks: privacyPolicyBlocks),
      ),
      GoRoute(
        path: '/terms-of-use',
        builder: (_, __) => const LegalDocScreen(title: 'Terms of Use', blocks: termsOfUseBlocks),
      ),
      GoRoute(path: '/journeys/history', builder: (_, __) => const JourneyHistoryScreen()),
      GoRoute(path: '/notifications', builder: (_, __) => const NotificationsScreen()),
      // Disruptions is gated behind AppConfig.disruptionsEnabled (default off):
      // when disabled the route redirects home so a stray deep-link can't reach
      // an empty/misleading board. See RELEASE_AUDIT.md.
      GoRoute(
        path: '/disruptions',
        redirect: (_, __) => AppConfig.disruptionsEnabled ? null : '/',
        builder: (_, __) => const DisruptionsScreen(),
      ),
      GoRoute(path: '/assistant', builder: (_, __) => const VoiceAssistantScreen()),
    ],
  );
});
