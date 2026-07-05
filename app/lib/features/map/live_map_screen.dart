import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:maplibre_gl/maplibre_gl.dart';

import '../../core/config.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/line_chip.dart';
import '../../core/widgets/live_indicator.dart';
import '../../core/widgets/stat_pill.dart';
import '../../domain/models/eta.dart';
import '../../domain/models/station.dart';
import '../../domain/models/train.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import 'train_animator.dart';

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

  static const _trainsSource = 'mp-trains';
  static const _stationsSource = 'mp-stations';
  static const _linesSource = 'mp-lines';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _animator.dispose();
    super.dispose();
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
              child: Row(
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
                      : IconPillButton(
                          icon: Icons.download_for_offline_rounded,
                          tooltip: 'Download offline map area',
                          onPressed: _downloadOfflineTiles,
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
        metadata: {'name': 'delhi-metro'},
      );
      messenger.showSnackBar(
          const SnackBar(content: Text('Map saved for offline use!')));
    } on Exception {
      messenger.showSnackBar(
          const SnackBar(content: Text("We couldn't save the map for offline use. Please try again.")));
    } finally {
      if (mounted) setState(() => _downloadingTiles = false);
    }
  }

  /// Hit-test the trains layer on tap (stable across maplibre_gl versions,
  /// unlike the feature-tap callback whose signature has churned).
  Future<void> _onMapClick(dynamic point, LatLng latLng) async {
    final map = _map;
    if (map == null) return;
    final features = await map.queryRenderedFeatures(
      point, ['mp-trains-layer'], null,
    );
    if (features.isEmpty) return;
    final first = features.first;
    final properties =
        (first is Map ? first['properties'] : null) as Map<dynamic, dynamic>?;
    final vehicleId = properties?['vehicleId']?.toString();
    if (vehicleId != null && vehicleId.isNotEmpty && mounted) {
      _showTrainSheet(vehicleId);
    }
  }

  // -- animation ---------------------------------------------------------------

  void _onTrains(Map<String, Train> trains) {
    if (!_styleReady) return;
    _latestTrains = trains;
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
              'properties': {'name': station.name},
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
    final speed = train.vehicle.speedMps;
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
              if (train.isStale) const Icon(Icons.signal_wifi_off_rounded, size: 16),
            ],
          ),
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
              if (speed != null)
                StatPill(icon: Icons.speed_rounded, label: 'Speed', value: '${(speed * 3.6).round()} km/h'),
              if (train.headsign != null)
                StatPill(icon: Icons.explore_rounded, label: 'Direction', value: train.headsign!),
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
