import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:maplibre_gl/maplibre_gl.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/config.dart';
import '../../core/design/app_colors.dart';
import '../../core/design/app_motion.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/root_shell.dart' show activeShellTabIndexProvider;
import '../../core/theme.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/live_indicator.dart';
import '../../core/widgets/stat_pill.dart';
import '../../data/ws_client.dart';
import '../../domain/models/eta.dart';
import '../../domain/models/station.dart';
import '../../domain/models/train.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import '../home/home_providers.dart' show favouriteStationsProvider;
import 'train_animator.dart';

/// Explore is the 3rd of 4 shell tabs (Home, Journey, Explore, You) — see
/// `RootShell`.
const _exploreTabIndex = 2;

/// The live network map: coloured line geometry, stations, and trains that
/// glide between GTFS updates. Tapping a train opens its live card.
class LiveMapScreen extends ConsumerStatefulWidget {
  const LiveMapScreen({super.key});

  @override
  ConsumerState<LiveMapScreen> createState() => _LiveMapScreenState();
}

class _LiveMapScreenState extends ConsumerState<LiveMapScreen>
    with WidgetsBindingObserver {
  MapLibreMapController? _map;
  bool _styleReady = false;
  late final TrainAnimator _animator =
      TrainAnimator(onFrame: (_) => _pushTrainSource());
  Map<String, Train> _latestTrains = const {};
  bool _downloadingTiles = false;

  /// Null while still checking; true once a saved 'delhi-metro' region is
  /// confirmed, so the download button can read as "already saved" instead
  /// of always prompting a first download.
  bool? _hasOfflineRegion;

  bool _showMapHint = false;
  Timer? _hintTimer;

  static const _trainsSource = 'mp-trains';
  static const _stationsSource = 'mp-stations';
  static const _linesSource = 'mp-lines';
  static const _offlineRegionName = 'delhi-metro';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _checkOfflineRegion();
    if (!ref.read(localStoreProvider).hasSeenMapHint) {
      _showMapHint = true;
      _hintTimer = Timer(const Duration(seconds: 4), _dismissMapHint);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _hintTimer?.cancel();
    _animator.dispose();
    super.dispose();
  }

  void _dismissMapHint() {
    _hintTimer?.cancel();
    if (!mounted || !_showMapHint) return;
    setState(() => _showMapHint = false);
    ref.read(localStoreProvider).markMapHintSeen();
  }

  Future<void> _checkOfflineRegion() async {
    try {
      final regions = await getListOfRegions();
      if (!mounted) return;
      setState(() => _hasOfflineRegion = regions.any((r) => r.metadata['name'] == _offlineRegionName));
    } on Exception {
      if (mounted) setState(() => _hasOfflineRegion = false);
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // No animation work while the map isn't on screen — battery hygiene.
    if (state == AppLifecycleState.paused) {
      _animator.pause();
    } else if (state == AppLifecycleState.resumed) {
      _animator.resume();
    }
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(liveTrainsProvider, (_, trains) => _onTrains(trains));
    ref.listen(activeShellTabIndexProvider, (_, next) {
      if (next == _exploreTabIndex) {
        _animator.resume();
      } else {
        _animator.pause();
      }
    });
    final wsStatus = ref.watch(wsStatusProvider).valueOrNull;
    final isReconnecting = wsStatus == WsStatus.reconnecting;
    // All trains share one backend source per deployment (see
    // VehiclePosition.source) -- checking one is as good as checking all,
    // but .any reads honestly even if that ever changes.
    final isEstimated = ref.watch(liveTrainsProvider).values.any((t) => t.isEstimated);

    // The map is the hero: full-bleed behind everything, with a couple of
    // small floating pills for status/controls rather than a solid app bar.
    return Scaffold(
      extendBody: true,
      body: Stack(
        children: [
          MapLibreMap(
            styleString: AppConfig.mapStyleUrl,
            initialCameraPosition: const CameraPosition(
              target: LatLng(AppConfig.initialLat, AppConfig.initialLon),
              zoom: AppConfig.initialZoom,
            ),
            onMapCreated: (controller) => _map = controller,
            onStyleLoadedCallback: _onStyleLoaded,
            onMapClick: _onMapClick,
            compassEnabled: false,
            rotateGesturesEnabled: false,
          ),
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      GlassSurface(
                        blur: true,
                        borderRadius: AppRadius.pillR,
                        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.md),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.map_rounded, size: 18, color: Theme.of(context).colorScheme.onSurface),
                            const SizedBox(width: AppSpacing.sm),
                            Text('Live map', style: Theme.of(context).textTheme.titleSmall),
                            const SizedBox(width: AppSpacing.sm),
                            const LiveIndicator(),
                          ],
                        ),
                      ),
                      const Spacer(),
                      IconPillButton(
                        icon: Icons.account_tree_rounded,
                        tooltip: 'Network map (diagram view)',
                        onPressed: () => context.push('/network-map'),
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      IconPillButton(
                        icon: Icons.search_rounded,
                        tooltip: 'Search stations',
                        onPressed: _openStationSearch,
                      ),
                      const SizedBox(width: AppSpacing.sm),
                      _downloadingTiles
                          ? const GlassSurface(
                              blur: true,
                              borderRadius: AppRadius.pillR,
                              padding: EdgeInsets.all(AppSpacing.md),
                              child: SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              ),
                            )
                          : Opacity(
                              opacity: 0.7,
                              child: IconPillButton(
                                icon: _hasOfflineRegion == true
                                    ? Icons.offline_pin_rounded
                                    : Icons.download_for_offline_rounded,
                                tooltip: 'Offline & maps',
                                onPressed: _openOfflineOptions,
                              ),
                            ),
                    ],
                  ),
                  if (isReconnecting) ...[
                    const SizedBox(height: AppSpacing.sm),
                    Text(
                      'Reconnecting — train positions may be a few minutes old.',
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(color: AppColors.danger),
                    ),
                  ],
                  if (isEstimated) ...[
                    const SizedBox(height: AppSpacing.sm),
                    GlassSurface(
                      blur: true,
                      borderRadius: AppRadius.pillR,
                      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.schedule_rounded, size: 14, color: AppColors.warning),
                          const SizedBox(width: AppSpacing.xs),
                          Flexible(
                            child: Text(
                              'Train positions are estimated from the schedule, not live GPS.',
                              style: Theme.of(context).textTheme.labelSmall?.copyWith(color: AppColors.warning),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                  if (MediaQuery.of(context).disableAnimations) ...[
                    if (_showMapHint) ...[
                      const SizedBox(height: AppSpacing.sm),
                      _MapHintPill(onDismiss: _dismissMapHint, isEstimated: isEstimated),
                    ],
                  ] else
                    AnimatedSwitcher(
                      duration: AppMotion.fast,
                      transitionBuilder: (child, animation) => FadeTransition(opacity: animation, child: child),
                      child: _showMapHint
                          ? Padding(
                              key: const ValueKey('map-hint'),
                              padding: const EdgeInsets.only(top: AppSpacing.sm),
                              child: _MapHintPill(onDismiss: _dismissMapHint, isEstimated: isEstimated),
                            )
                          : const SizedBox.shrink(key: ValueKey('no-map-hint')),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _onStyleLoaded() async {
    final map = _map;
    if (map == null) return;
    final bundle = ref.read(offlineBundleProvider).valueOrNull;

    await map.addSource(
        _linesSource, GeojsonSourceProperties(data: _lineGeoJson(bundle)));
    await map.addLineLayer(
      _linesSource,
      'mp-lines-layer',
      const LineLayerProperties(
        lineColor: ['get', 'color'],
        lineWidth: 3.5,
        lineOpacity: 0.85,
      ),
    );

    await map.addSource(
        _stationsSource, GeojsonSourceProperties(data: _stationGeoJson(bundle)));
    await map.addCircleLayer(
      _stationsSource,
      'mp-stations-layer',
      const CircleLayerProperties(
        circleRadius: 4,
        circleColor: '#ffffff',
        circleStrokeWidth: 2,
        circleStrokeColor: '#444444',
      ),
    );
    // Station name labels appear once zoomed in enough to be readable.
    await map.addSymbolLayer(
      _stationsSource,
      'mp-station-labels',
      const SymbolLayerProperties(
        textField: ['get', 'name'],
        textSize: 11,
        textOffset: [0, 1.1],
        textAnchor: 'top',
        textHaloColor: '#ffffff',
        textHaloWidth: 1.2,
      ),
      minzoom: 12,
    );

    // Trains cluster when zoomed out so a 300-train network stays readable.
    await map.addSource(
      _trainsSource,
      GeojsonSourceProperties(
        data: _trainGeoJson(),
        cluster: true,
        clusterMaxZoom: 11,
        clusterRadius: 40,
      ),
    );
    await map.addCircleLayer(
      _trainsSource,
      'mp-train-clusters',
      const CircleLayerProperties(
        circleRadius: 16,
        circleColor: '#1F6FEB',
        circleOpacity: 0.85,
      ),
      filter: ['has', 'point_count'],
    );
    await map.addSymbolLayer(
      _trainsSource,
      'mp-train-cluster-count',
      const SymbolLayerProperties(
        textField: ['get', 'point_count_abbreviated'],
        textSize: 12,
        textColor: '#ffffff',
      ),
      filter: ['has', 'point_count'],
    );
    await map.addCircleLayer(
      _trainsSource,
      'mp-trains-layer',
      const CircleLayerProperties(
        circleRadius: 8,
        circleColor: ['get', 'color'],
        circleStrokeWidth: 2,
        circleStrokeColor: '#ffffff',
      ),
      filter: [
        '!',
        ['has', 'point_count'],
      ],
    );

    _styleReady = true;
    _onTrains(ref.read(liveTrainsProvider));
    unawaited(_flyToHomeIfKnown(map, bundle));
  }

  /// A daily commuter opening the map is almost always checking on their own
  /// line, not the whole network — if a 'Home' favourite is known, start
  /// there instead of the full-network overview.
  Future<void> _flyToHomeIfKnown(MapLibreMapController map, OfflineBundle? bundle) async {
    if (bundle == null) return;
    List<Map<String, dynamic>> favourites;
    try {
      favourites = await ref.read(favouriteStationsProvider.future);
    } on Exception {
      return;
    }
    if (!mounted) return;
    Map<String, dynamic>? home;
    for (final favourite in favourites) {
      if ('${favourite['label']}'.toLowerCase() == 'home') {
        home = favourite;
        break;
      }
    }
    if (home == null) return;
    final stopId = '${home['stop_id']}';
    final station = bundle.stations.where((s) => s.stopId == stopId).firstOrNull;
    if (station == null) return;
    await _flyToStation(station, zoom: 14);
  }

  /// Animates the camera to a station, e.g. after a map-picker search.
  Future<void> _flyToStation(Station station, {double zoom = 15}) async {
    await _map?.animateCamera(CameraUpdate.newLatLngZoom(LatLng(station.lat, station.lon), zoom));
  }

  /// Opens the station-only search picker; flies the map to whatever the
  /// user picks rather than opening its detail page.
  Future<void> _openStationSearch() async {
    final station = await context.push<Station>('/search?mapPicker=true');
    if (station != null && mounted) {
      await _flyToStation(station);
    }
  }

  /// The offline/maps menu: cache tiles for the live map, or grab DMRC's
  /// official network-map PDF for offline reference.
  void _openOfflineOptions() {
    showAppBottomSheet<void>(
      context,
      builder: (sheetContext) => Padding(
        padding: const EdgeInsets.fromLTRB(
            AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Offline & maps', style: Theme.of(sheetContext).textTheme.titleLarge),
            const SizedBox(height: AppSpacing.md),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(
                _hasOfflineRegion == true
                    ? Icons.offline_pin_rounded
                    : Icons.download_for_offline_rounded,
              ),
              title: Text(_hasOfflineRegion == true
                  ? 'Refresh saved offline area'
                  : 'Save this area for offline use'),
              subtitle: const Text('Caches the live map tiles for the Delhi region'),
              onTap: () {
                Navigator.of(sheetContext).pop();
                _downloadOfflineTiles();
              },
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.map_outlined),
              title: const Text('Official DMRC network map (PDF)'),
              subtitle: const Text('Opens DMRC\'s official map to view or save'),
              trailing: const Icon(Icons.open_in_new_rounded, size: 18),
              onTap: () {
                Navigator.of(sheetContext).pop();
                _openDmrcMap();
              },
            ),
          ],
        ),
      ),
    );
  }

  /// Open DMRC's own hosted, publicly-downloadable network-map PDF in the
  /// browser. We link to their official file rather than bundling a copy —
  /// the map artwork is DMRC's copyright.
  Future<void> _openDmrcMap() async {
    final messenger = ScaffoldMessenger.of(context);
    final ok = await launchUrl(
      Uri.parse(AppConfig.dmrcNetworkMapUrl),
      mode: LaunchMode.externalApplication,
    );
    if (!ok) {
      messenger.showSnackBar(
        const SnackBar(content: Text("Couldn't open the DMRC map — check your connection.")),
      );
    }
  }

  /// Cache map tiles for the Delhi metro region so the map renders offline.
  Future<void> _downloadOfflineTiles() async {
    setState(() => _downloadingTiles = true);
    final messenger = ScaffoldMessenger.of(context);
    try {
      await downloadOfflineRegion(
        OfflineRegionDefinition(
          bounds: LatLngBounds(
            southwest: const LatLng(28.35, 76.85),
            northeast: const LatLng(28.90, 77.55),
          ),
          mapStyleUrl: AppConfig.mapStyleUrl,
          minZoom: 9,
          maxZoom: 13,
        ),
        metadata: {'name': _offlineRegionName},
      );
      if (mounted) setState(() => _hasOfflineRegion = true);
      messenger.showSnackBar(
          const SnackBar(content: Text('Map saved for offline use!')));
    } on Exception {
      messenger.showSnackBar(
          const SnackBar(content: Text("We couldn't save the map for offline use. Please try again.")));
    } finally {
      if (mounted) setState(() => _downloadingTiles = false);
    }
  }

  /// Hit-test trains, stations, and train clusters on tap (stable across
  /// maplibre_gl versions, unlike the feature-tap callback whose signature
  /// has churned). A train opens its live card; a station jumps straight to
  /// its detail screen; a cluster zooms in on itself rather than requiring a
  /// manual pinch.
  Future<void> _onMapClick(Point<double> point, LatLng latLng) async {
    final map = _map;
    if (map == null) return;
    const layers = ['mp-trains-layer', 'mp-stations-layer', 'mp-train-clusters'];
    var features = await map.queryRenderedFeatures(point, layers, null);
    if (features.isEmpty) {
      // Trains are small circles — a slightly-off tap can miss the exact
      // pixel. Widen the hit-test to a small screen-space box around the
      // tap before giving up entirely.
      features = await map.queryRenderedFeaturesInRect(
        Rect.fromCenter(center: Offset(point.x, point.y), width: 24, height: 24),
        layers,
        null,
      );
    }
    if (features.isEmpty) return;
    final first = features.first;
    final properties =
        (first is Map ? first['properties'] : null) as Map<dynamic, dynamic>?;

    final vehicleId = properties?['vehicleId']?.toString();
    if (vehicleId != null && vehicleId.isNotEmpty && mounted) {
      _showTrainSheet(vehicleId);
      return;
    }

    final stopId = properties?['stopId']?.toString();
    if (stopId != null && stopId.isNotEmpty && mounted) {
      context.push('/station/$stopId');
      return;
    }

    if (properties?['point_count'] != null) {
      final geometry = (first is Map ? first['geometry'] : null) as Map<dynamic, dynamic>?;
      final coordinates = geometry?['coordinates'] as List<dynamic>?;
      if (coordinates == null || coordinates.length < 2) return;
      final lon = (coordinates[0] as num).toDouble();
      final lat = (coordinates[1] as num).toDouble();
      final currentZoom = map.cameraPosition?.zoom ?? AppConfig.initialZoom;
      await map.animateCamera(CameraUpdate.newLatLngZoom(LatLng(lat, lon), currentZoom + 2));
    }
  }

  // -- animation ---------------------------------------------------------------

  void _onTrains(Map<String, Train> trains) {
    if (!_styleReady) return;
    _latestTrains = trains;
    // The shell keeps every tab's widgets alive (IndexedStack), so this
    // fires even while a different tab is on screen — only feed the
    // animator (and its platform-channel pushes) while Explore is actually
    // visible. Battery hygiene, same spirit as the app-lifecycle pause.
    if (ref.read(activeShellTabIndexProvider) != _exploreTabIndex) return;
    _animator.applyPositions({
      for (final train in trains.values)
        train.id: (train.vehicle.latitude, train.vehicle.longitude),
    });
  }

  Future<void> _pushTrainSource() async {
    await _map?.setGeoJsonSource(_trainsSource, _trainGeoJson());
  }

  // -- geojson builders ----------------------------------------------------------

  Map<String, dynamic> _trainGeoJson() => {
        'type': 'FeatureCollection',
        'features': [
          for (final entry in _animator.trains.entries)
            {
              'type': 'Feature',
              'properties': {
                'vehicleId': entry.key,
                'color': routeColorHex(
                  _latestTrains[entry.key]?.routeColor,
                  _latestTrains[entry.key]?.lineLabel,
                ),
              },
              'geometry': {
                'type': 'Point',
                'coordinates': [entry.value.lon, entry.value.lat],
              },
            },
        ],
      };

  Map<String, dynamic> _stationGeoJson(OfflineBundle? bundle) => {
        'type': 'FeatureCollection',
        'features': [
          for (final station in bundle?.stations ?? const <Station>[])
            {
              'type': 'Feature',
              'properties': {'name': station.name, 'stopId': station.stopId},
              'geometry': {
                'type': 'Point',
                'coordinates': [station.lon, station.lat],
              },
            },
        ],
      };

  Map<String, dynamic> _lineGeoJson(OfflineBundle? bundle) {
    if (bundle == null) return const {'type': 'FeatureCollection', 'features': []};
    final byId = {for (final s in bundle.stations) s.stopId: s};
    final colors = {for (final r in bundle.routes) r.routeId: r.color};
    final names = {for (final r in bundle.routes) r.routeId: r.longName ?? r.shortName};
    final features = <Map<String, dynamic>>[];
    for (final entry in bundle.routeStations.entries) {
      final sequence = entry.value['0'] ?? entry.value.values.firstOrNull;
      if (sequence == null || sequence.length < 2) continue;
      features.add({
        'type': 'Feature',
        'properties': {
          'color': routeColorHex(colors[entry.key], names[entry.key]),
        },
        'geometry': {
          'type': 'LineString',
          'coordinates': [
            for (final stopId in sequence)
              if (byId[stopId] != null) [byId[stopId]!.lon, byId[stopId]!.lat],
          ],
        },
      });
    }
    return {'type': 'FeatureCollection', 'features': features};
  }

  // -- train sheet -------------------------------------------------------------

  void _showTrainSheet(String vehicleId) {
    showAppBottomSheet<void>(
      context,
      builder: (_) => _TrainSheet(vehicleId: vehicleId),
    );
  }
}

/// The one-time "dots are trains" pill shown until the user taps it away.
class _MapHintPill extends StatelessWidget {
  const _MapHintPill({required this.onDismiss, required this.isEstimated});

  final VoidCallback onDismiss;
  final bool isEstimated;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onDismiss,
      child: GlassSurface(
        blur: true,
        borderRadius: AppRadius.pillR,
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.sm),
        child: Text(
          isEstimated ? 'Dots are trains, estimated from the schedule' : 'Dots are trains, moving live',
          style: Theme.of(context).textTheme.labelSmall,
        ),
      ),
    );
  }
}

/// The tap-a-train card: line, motion state, next station, minutes away.
class _TrainSheet extends ConsumerWidget {
  const _TrainSheet({required this.vehicleId});

  final String vehicleId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final train = ref.watch(liveTrainProvider(vehicleId));
    final theme = Theme.of(context);
    if (train == null) {
      return const Padding(
        padding: EdgeInsets.all(32),
        child: Text("We've lost track of this train — it may have finished its trip."),
      );
    }
    final next = train.nextStation;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 0, 20, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LineChip(label: train.lineLabel, colorHex: train.routeColor),
          const SizedBox(height: AppSpacing.md),
          Row(
            children: [
              Icon(
                train.atStation ? Icons.subway_rounded : Icons.directions_subway_filled,
                color: routeColor(train.routeColor, train.lineLabel),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  train.atStation ? 'At ${train.currentStation?.name ?? 'station'}' : 'Moving train',
                  style: theme.textTheme.titleMedium,
                ),
              ),
              if (train.isStale) ...[
                const Icon(Icons.signal_wifi_off_rounded, size: 16),
                const SizedBox(width: AppSpacing.xs),
                Text(
                  'Position may be a few minutes old',
                  style: theme.textTheme.labelSmall,
                ),
              ],
            ],
          ),
          if (train.isEstimated) ...[
            const SizedBox(height: AppSpacing.xs),
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.schedule_rounded, size: 14, color: AppColors.warning),
                const SizedBox(width: AppSpacing.xs),
                Text(
                  'Estimated from the schedule, not live GPS',
                  style: theme.textTheme.labelSmall?.copyWith(color: AppColors.warning),
                ),
              ],
            ),
          ],
          if (next != null) ...[
            const SizedBox(height: AppSpacing.md),
            Text('Next: ${next.name}', style: theme.textTheme.headlineSmall),
            _NextStopEta(vehicleId: vehicleId),
          ],
          const SizedBox(height: AppSpacing.lg),
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.md,
            children: [
              if (train.currentStation != null)
                StatPill(icon: Icons.my_location_rounded, label: 'Current', value: train.currentStation!.name),
              if (train.destination != null)
                StatPill(icon: Icons.flag_rounded, label: 'Destination', value: train.destination!.name),
            ],
          ),
          if (train.remainingStations.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.lg),
            Text('Remaining stations', style: theme.textTheme.labelMedium),
            const SizedBox(height: AppSpacing.sm),
            SizedBox(
              height: 36,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                itemCount: train.remainingStations.length,
                separatorBuilder: (_, __) => const Icon(Icons.chevron_right_rounded, size: 16),
                itemBuilder: (_, index) => Chip(
                  visualDensity: VisualDensity.compact,
                  label: Text(train.remainingStations[index].name, style: const TextStyle(fontSize: 12)),
                ),
              ),
            ),
          ],
          const SizedBox(height: AppSpacing.xl),
          PrimaryButton(
            label: 'See train details',
            expand: true,
            onPressed: () {
              Navigator.of(context).pop();
              context.push('/train/$vehicleId');
            },
          ),
        ],
      ),
    );
  }
}

/// '2 min' to the next station; refetched whenever this train's WS state
/// changes (event-driven — never a polling loop).
class _NextStopEta extends ConsumerWidget {
  const _NextStopEta({required this.vehicleId});

  final String vehicleId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final train = ref.watch(liveTrainProvider(vehicleId));
    final eta = ref.watch(_etaProvider(
        (vehicleId, train?.vehicle.timestamp.toIso8601String() ?? '')));
    final seconds = eta.valueOrNull?.nextStation?.etaSeconds;
    return Text(
      minutesLabel(seconds),
      style: Theme.of(context)
          .textTheme
          .headlineMedium
          ?.copyWith(fontWeight: FontWeight.w800),
    );
  }
}

/// Keyed by (vehicleId, feed timestamp): a new position invalidates the ETA.
final _etaProvider = FutureProvider.autoDispose
    .family<VehicleEta?, (String, String)>((ref, key) async {
  final repository = ref.watch(trainsRepositoryProvider);
  return repository.eta(key.$1);
});
