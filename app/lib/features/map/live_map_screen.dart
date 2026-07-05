import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:maplibre_gl/maplibre_gl.dart';

import '../../core/config.dart';
import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../domain/models/eta.dart';
import '../../domain/models/station.dart';
import '../../domain/models/train.dart';
import '../../providers/core_providers.dart';
import '../../providers/live_providers.dart';
import '../shared/widgets.dart';
import 'train_animator.dart';

/// The live network map: coloured line geometry, stations, and trains that
/// glide between GTFS updates. Tapping a train opens its live card.
class LiveMapScreen extends ConsumerStatefulWidget {
  const LiveMapScreen({super.key});

  @override
  ConsumerState<LiveMapScreen> createState() => _LiveMapScreenState();
}

class _LiveMapScreenState extends ConsumerState<LiveMapScreen> {
  MapLibreMapController? _map;
  bool _styleReady = false;
  late final TrainAnimator _animator =
      TrainAnimator(onFrame: (_) => _pushTrainSource());
  Map<String, Train> _latestTrains = const {};

  static const _trainsSource = 'mp-trains';
  static const _stationsSource = 'mp-stations';
  static const _linesSource = 'mp-lines';

  @override
  void dispose() {
    _animator.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(liveTrainsProvider, (_, trains) => _onTrains(trains));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Live map'),
        actions: const [
          Padding(padding: EdgeInsets.only(right: 16), child: Center(child: LiveIndicator())),
        ],
      ),
      body: MapLibreMap(
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

    await map.addSource(
        _trainsSource, GeojsonSourceProperties(data: _trainGeoJson()));
    await map.addCircleLayer(
      _trainsSource,
      'mp-trains-layer',
      const CircleLayerProperties(
        circleRadius: 8,
        circleColor: ['get', 'color'],
        circleStrokeWidth: 2,
        circleStrokeColor: '#ffffff',
      ),
    );

    _styleReady = true;
    _onTrains(ref.read(liveTrainsProvider));
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
                'color':
                    '#${(_latestTrains[entry.key]?.routeColor ?? '1F6FEB').replaceAll('#', '')}',
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
    final features = <Map<String, dynamic>>[];
    for (final entry in bundle.routeStations.entries) {
      final sequence = entry.value['0'] ?? entry.value.values.firstOrNull;
      if (sequence == null || sequence.length < 2) continue;
      features.add({
        'type': 'Feature',
        'properties': {
          'color': '#${(colors[entry.key] ?? '1F6FEB').replaceAll('#', '')}',
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
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
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
        child: Text('This train is no longer tracked.'),
      );
    }
    final next = train.nextStation;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 0, 24, 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LineBadge(label: train.lineLabel, colorHex: train.routeColor),
          const SizedBox(height: 12),
          Row(
            children: [
              Icon(
                train.atStation ? Icons.subway : Icons.directions_subway_filled,
                color: routeColor(train.routeColor),
              ),
              const SizedBox(width: 8),
              Text(
                train.atStation
                    ? 'At ${train.currentStation?.name ?? 'station'}'
                    : 'Moving train',
                style: theme.textTheme.titleMedium,
              ),
              if (train.isStale) ...[
                const SizedBox(width: 8),
                const Icon(Icons.signal_wifi_off, size: 16),
              ],
            ],
          ),
          if (next != null) ...[
            const SizedBox(height: 12),
            Text('Next: ${next.name}', style: theme.textTheme.titleLarge),
            _NextStopEta(vehicleId: vehicleId),
          ],
          const SizedBox(height: 16),
          FilledButton.tonal(
            onPressed: () {
              Navigator.of(context).pop();
              context.push('/train/$vehicleId');
            },
            child: const Text('Train details'),
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
