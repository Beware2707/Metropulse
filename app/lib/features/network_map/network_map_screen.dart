import 'dart:math' as math;

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/formatters.dart';
import '../../core/theme.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/line_chip.dart';
import '../../data/api_client.dart';
import '../../domain/fare.dart';
import '../../domain/models/journey.dart';
import '../../domain/models/station.dart';
import '../../domain/network_map_geometry.dart';
import '../../domain/network_schematic.dart';
import '../../providers/core_providers.dart';
import '../shared/station_search_sheet.dart';

/// The precomputed octilinear schematic asset. Erroring (asset absent from
/// the bundle, malformed JSON, failed validation) is a designed-for state:
/// the screen branches on this provider's AsyncValue and falls back to the
/// live geographic projection, so the map never breaks.
final networkSchematicProvider = FutureProvider<NetworkSchematic>(
  (ref) => NetworkSchematic.loadFromAsset(),
);

/// Reachability-mode buckets: the colour a station dot takes given how many
/// whole minutes it is from the picked origin (origin itself is 0). A pure,
/// top-level function so the bucket cut-offs are unit-testable without a
/// painter or a widget. Cut-offs are half-open lower-inclusive — 15 is the
/// first amber minute, 30 the first orange, 45 the first red, 60 the first
/// deep red — so every boundary minute lands unambiguously in one bucket.
/// Two palettes: brighter, higher-chroma dots on the dark canvas; deeper,
/// more saturated dots on the warm-white light canvas, so the ramp stays
/// legible against either surface.
Color reachBucketColor(int minutes, {required bool dark}) {
  final bucket = minutes < 15
      ? 0
      : minutes < 30
          ? 1
          : minutes < 45
              ? 2
              : minutes < 60
                  ? 3
                  : 4;
  const light = <Color>[
    Color(0xFF1F9E4B), // <15  green
    Color(0xFFC98A00), // 15-30 amber
    Color(0xFFE0680C), // 30-45 orange
    Color(0xFFD8362C), // 45-60 red
    Color(0xFF8E1B14), // 60+  deep red
  ];
  const dark_ = <Color>[
    Color(0xFF4ADE80), // <15  green
    Color(0xFFFACC15), // 15-30 amber
    Color(0xFFFB923C), // 30-45 orange
    Color(0xFFF87171), // 45-60 red
    Color(0xFFDC2626), // 60+  deep red
  ];
  return (dark ? dark_ : light)[bucket];
}

/// The reach-mode legend, in order: label + the exact dot colour
/// [reachBucketColor] paints for a representative minute in each bucket.
List<(String, Color)> reachLegend({required bool dark}) => [
      ('<15 min', reachBucketColor(0, dark: dark)),
      ('15-30', reachBucketColor(15, dark: dark)),
      ('30-45', reachBucketColor(30, dark: dark)),
      ('45-60', reachBucketColor(45, dark: dark)),
      ('60+', reachBucketColor(60, dark: dark)),
    ];

/// A DMRC-style schematic network diagram: coloured lines through real
/// station geometry, interchanges marked, with a picked journey highlighted on
/// the diagram and broken down in a panel. Deliberately CustomPaint-drawn
/// (not MapLibre tiles) for the clean, offline, basemap-free "map view" look.
///
/// Everything is honest: line colours and geometry come straight from the
/// offline bundle, the route + timing come from the same journey planner the
/// rest of the app uses, and fare is the shared client-side *estimate*. DMRC's
/// own map shows a platform number per leg; that lives only in DMRC's private
/// API (which this app deliberately does not use), so it is omitted entirely
/// rather than faked.
class NetworkMapScreen extends ConsumerStatefulWidget {
  const NetworkMapScreen({super.key, this.initialOriginId, this.initialDestinationId});

  final String? initialOriginId;
  final String? initialDestinationId;

  @override
  ConsumerState<NetworkMapScreen> createState() => _NetworkMapScreenState();
}

class _NetworkMapScreenState extends ConsumerState<NetworkMapScreen> {
  final TransformationController _transform = TransformationController();

  /// Laid-out label TextPainters, shared across every painter construction so
  /// a repaint never re-lays-out text (262 stations x TextPainter.layout per
  /// frame was a large part of the pan/zoom jank). Theme changes are handled
  /// by folding the label/halo colour into each cache key rather than by a
  /// lifecycle hook: a stale-theme entry is simply never hit again, and growth
  /// is bounded in practice (stations x 2 variants x 2 opacities per palette,
  /// and users switch themes rarely).
  final Map<String, TextPainter> _tpCache = <String, TextPainter>{};

  Station? _origin;
  Station? _destination;
  JourneyPlan? _plan;
  bool _loading = false;
  String? _error;
  bool _resolvedInitialStations = false;

  /// Reachability ("isochrone") mode. When [_reachMode] is off, every field
  /// below is null and the map behaves exactly as the tap-to-plan map always
  /// has — the painter receives a null reach map and draws nothing new.
  /// When on, tapping a station fetches its timetable reach and tints every
  /// dot by minutes-from-origin instead of planning a trip.
  bool _reachMode = false;
  String? _reachOrigin;
  Map<String, int>? _reachMinutes;

  @override
  void dispose() {
    _transform.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bundle = ref.watch(offlineBundleProvider).valueOrNull;
    final schematicAsync = ref.watch(networkSchematicProvider);
    final schematic = schematicAsync.valueOrNull;

    if (!_resolvedInitialStations && bundle != null) {
      _resolvedInitialStations = true;
      final byId = {for (final s in bundle.stations) s.stopId: s};
      _origin ??= byId[widget.initialOriginId];
      _destination ??= byId[widget.initialDestinationId];
      if (_origin != null && _destination != null) {
        WidgetsBinding.instance.addPostFrameCallback((_) => _planJourney());
      }
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Network map')),
      body: bundle == null || bundle.stations.isEmpty
          ? const Center(child: CircularProgressIndicator())
          : Stack(
              children: [
                Positioned.fill(child: _buildDiagram(bundle, schematicAsync)),
                Positioned(
                  top: 0,
                  left: 0,
                  right: 0,
                  child: SafeArea(
                    bottom: false,
                    child: Padding(
                      padding: const EdgeInsets.all(AppSpacing.lg),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          _EndpointBar(
                            origin: _origin,
                            destination: _destination,
                            onPickOrigin: () => _pick(isOrigin: true),
                            onPickDestination: () => _pick(isOrigin: false),
                            onSwap: _origin != null && _destination != null ? _swap : null,
                            reachMode: _reachMode,
                            onToggleReach: _toggleReach,
                          ),
                          if (schematic != null) ...[
                            const SizedBox(height: AppSpacing.sm),
                            _LineLegend(lines: schematic.lines),
                          ],
                          if (_reachMode) ...[
                            const SizedBox(height: AppSpacing.sm),
                            _ReachOverlayBar(
                              originName: _reachOrigin == null
                                  ? null
                                  : ref.read(stationIndexProvider)[_reachOrigin]?.name,
                              showLegend: _reachMinutes != null,
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
                if (_loading)
                  const Positioned(
                    top: 140,
                    left: 0,
                    right: 0,
                    child: Center(child: _LoadingPill()),
                  ),
                if (_error != null)
                  Positioned(
                    top: 140,
                    left: AppSpacing.lg,
                    right: AppSpacing.lg,
                    child: _ErrorPill(message: _error!),
                  ),
                if (_plan != null)
                  _JourneyPanel(
                    plan: _plan!,
                    onClear: _clearPlan,
                  ),
              ],
            ),
    );
  }

  Widget _buildDiagram(OfflineBundle bundle, AsyncValue<NetworkSchematic> schematicAsync) {
    return schematicAsync.when(
      data: (schematic) => _buildAssetDiagram(bundle, schematic),
      // The asset is bundled, so loading resolves within a frame or two; a
      // bare spinner avoids flashing the geographic layout first.
      loading: () => const Center(child: CircularProgressIndicator()),
      // Missing/unparseable asset: the pre-asset geographic rendering, intact.
      error: (_, __) => _buildGeographicDiagram(bundle),
    );
  }

  // -- asset-drawn schematic path ---------------------------------------------

  /// Cached design-space station positions: asset positions for stations the
  /// schematic knows, affine-fitted geo positions for bundle stations the
  /// asset predates. Rebuilt only when the bundle or schematic instance
  /// changes, so painting and hit-testing share one stable map.
  Map<String, Offset>? _designPoints;
  Set<String>? _designExtras;
  OfflineBundle? _designPointsBundle;
  NetworkSchematic? _designPointsSchematic;

  void _ensureDesignPoints(OfflineBundle bundle, NetworkSchematic schematic) {
    if (_designPoints != null &&
        identical(_designPointsBundle, bundle) &&
        identical(_designPointsSchematic, schematic)) {
      return;
    }
    final points = <String, Offset>{};
    final missing = <Station>[];
    final common = <Station>[];
    for (final station in bundle.stations) {
      final position = schematic.positionOf(station.stopId);
      if (position != null) {
        points[station.stopId] = position;
        common.add(station);
      } else {
        missing.add(station);
      }
    }
    final extras = <String>{};
    if (missing.isNotEmpty) {
      // Stations added to the feed after the asset was generated: place them
      // via a least-squares affine fit (lat,lon)->(x,y) over every station
      // present in both, so they land in roughly the right neighbourhood.
      final fit = _AffineGeoFit.fromStations(common, schematic);
      if (fit != null) {
        for (final station in missing) {
          points[station.stopId] = fit.apply(station.lat, station.lon);
          extras.add(station.stopId);
        }
      }
    }
    _designPoints = points;
    _designExtras = extras;
    _designPointsBundle = bundle;
    _designPointsSchematic = schematic;
  }

  /// Applied exactly once: the initial camera that fits the whole design-space
  /// canvas into the viewport, centred.
  bool _appliedInitialCamera = false;

  Widget _buildAssetDiagram(OfflineBundle bundle, NetworkSchematic schematic) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    _ensureDesignPoints(bundle, schematic);
    final points = _designPoints!;
    final extras = _designExtras!;
    final extraNames = <String, String>{
      if (extras.isNotEmpty)
        for (final s in bundle.stations)
          if (extras.contains(s.stopId)) s.stopId: s.name,
    };

    final drawnLines = [
      for (final line in schematic.lines)
        if (line.points.length >= 2)
          _LinePolyline(
            color: routeColor(line.color, line.lineKey),
            points: line.points,
          ),
    ];

    final overlay = _plan == null ? null : _buildAssetOverlay(_plan!, schematic, points);

    return LayoutBuilder(
      builder: (context, constraints) {
        final canvas = schematic.canvas;
        var fit = math.min(
          constraints.maxWidth / canvas.width,
          constraints.maxHeight / canvas.height,
        );
        if (!fit.isFinite || fit <= 0) fit = 1.0;
        if (!_appliedInitialCamera) {
          _appliedInitialCamera = true;
          // Safe to assign during build: nothing listens to the controller
          // yet on the first asset-path build (the loading branch above has
          // no InteractiveViewer), so no notify-during-build hazard.
          _transform.value = Matrix4.identity()
            ..translateByDouble(
              (constraints.maxWidth - canvas.width * fit) / 2,
              (constraints.maxHeight - canvas.height * fit) / 2,
              0,
              1,
            )
            ..scaleByDouble(fit, fit, fit, 1);
        }
        return InteractiveViewer(
          transformationController: _transform,
          constrained: false,
          minScale: 0.9 * fit,
          maxScale: math.max(3.5, fit),
          boundaryMargin: const EdgeInsets.all(double.infinity),
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            // localPosition is in the child's (design) space, so hit-testing
            // works directly against asset coordinates at any zoom.
            onTapUp: (details) =>
                _onCanvasTap(details.localPosition, points, hitRadius: 26),
            // No AnimatedBuilder here: asset labels are always drawn (their
            // placement is precomputed and collision-free), so nothing about
            // the painter depends on the zoom level. The RepaintBoundary
            // keeps pan/zoom a pure re-composite of the cached layer.
            child: RepaintBoundary(
              child: CustomPaint(
                size: canvas,
                painter: _AssetSchematicPainter(
                  lines: drawnLines,
                  stations: schematic.stations,
                  extraPoints: {
                    for (final id in extras)
                      if (points[id] != null) id: points[id]!,
                  },
                  extraNames: extraNames,
                  stationPoints: points,
                  overlay: overlay,
                  labelColor: scheme.onSurface,
                  haloColor: scheme.surface,
                  stationFill: scheme.surface,
                  stationBorder: scheme.onSurface.withValues(alpha: 0.75),
                  textPainterCache: _tpCache,
                  // Reach tinting is strictly opt-in: null whenever the mode
                  // is off, so paint() takes the untouched original path.
                  reachMinutes: _reachMode ? _reachMinutes : null,
                  reachOrigin: _reachMode ? _reachOrigin : null,
                  dark: theme.brightness == Brightness.dark,
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  /// The journey overlay in design space: each ride leg follows the drawn
  /// line's exact bends (sliced via stopPointIndex), matched by the leg's
  /// route_id first, then by line key; a straight station-to-station polyline
  /// is the last resort so an unmatched leg still shows.
  _RouteOverlay _buildAssetOverlay(
    JourneyPlan plan,
    NetworkSchematic schematic,
    Map<String, Offset> points,
  ) {
    final stopIds = <String>{plan.origin.stopId, plan.destination.stopId};
    final highlightLines = <_LinePolyline>[];
    for (final leg in plan.legs) {
      final legStops = leg.stations ?? [leg.board, leg.alight];
      for (final stop in legStops) {
        stopIds.add(stop.stopId);
      }
      if (!leg.isRide) continue;
      List<Offset>? polyline;
      final routeId = leg.routeId;
      if (routeId != null) {
        polyline = schematic.segmentBetween(routeId, leg.board.stopId, leg.alight.stopId);
      }
      polyline ??= schematic.segmentBetween(
        lineKeyForRoute(routeId ?? '', leg.routeLongName),
        leg.board.stopId,
        leg.alight.stopId,
      );
      polyline ??= [
        for (final stop in legStops)
          if (points[stop.stopId] != null) points[stop.stopId]!,
      ];
      if (polyline.length < 2) continue;
      highlightLines.add(_LinePolyline(
        color: routeColor(leg.routeColor, leg.routeLongName),
        points: polyline,
      ));
    }
    return _RouteOverlay(
      stopIds: stopIds,
      boardStopId: plan.origin.stopId,
      alightStopId: plan.destination.stopId,
      interchangeStopIds: plan.interchangeStopIds.toSet(),
      lines: highlightLines,
    );
  }

  // -- geographic fallback path -------------------------------------------------

  Widget _buildGeographicDiagram(OfflineBundle bundle) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = Size(constraints.maxWidth, constraints.maxHeight);
        final bounds = GeoBounds.fromStations(bundle.stations);
        if (bounds == null) return const SizedBox.shrink();
        final projection = SchematicProjection(bounds: bounds, size: size, padding: 44);

        final byId = {for (final s in bundle.stations) s.stopId: s};
        final points = {
          for (final s in bundle.stations) s.stopId: projection.projectStation(s),
        };
        // Line identity comes from the long-name prefix ('RED_Rithala to
        // Dilshad Garden' -> 'RED'): the DMRC feed models each direction as a
        // separate route_id, so counting raw route_ids would mark every stop
        // an interchange. Deliberately NOT falling back to shortName here —
        // its prefix is ambiguous ('R_SP_R' is RAPID, 'R_RD' is RED);
        // lineKeyForRoute falls back to the routeId itself instead.
        final lineKeyByRoute = {
          for (final r in bundle.routes)
            r.routeId: lineKeyForRoute(r.routeId, r.longName),
        };
        final interchanges = detectInterchanges(
          bundle.routeStations,
          lineKeyByRoute: lineKeyByRoute,
        );

        final colorByRoute = {for (final r in bundle.routes) r.routeId: r.color};
        final nameByRoute = {
          for (final r in bundle.routes) r.routeId: r.longName ?? r.shortName,
        };

        final lines = <_LinePolyline>[];
        for (final entry in bundle.routeStations.entries) {
          final sequence = routeDrawSequence(entry.value);
          if (sequence == null) continue;
          final polyline = [
            for (final stopId in sequence)
              if (points[stopId] != null) points[stopId]!,
          ];
          if (polyline.length < 2) continue;
          lines.add(_LinePolyline(
            color: routeColor(colorByRoute[entry.key], nameByRoute[entry.key]),
            points: polyline,
          ));
        }

        final overlay = _plan == null ? null : _buildOverlay(_plan!, byId, points);

        return InteractiveViewer(
          transformationController: _transform,
          minScale: 0.6,
          maxScale: 7,
          boundaryMargin: const EdgeInsets.all(600),
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapUp: (details) => _onCanvasTap(details.localPosition, points),
            child: AnimatedBuilder(
              animation: _transform,
              builder: (context, _) {
                final viewScale = _transform.value.getMaxScaleOnAxis();
                // The RepaintBoundary gives the diagram its own layer, so
                // InteractiveViewer's per-gesture-frame Transform re-composites
                // the cached layer instead of re-running paint() every frame.
                // The AnimatedBuilder still rebuilds to deliver labelScale, but
                // with the bucket-based shouldRepaint an actual repaint only
                // happens when a label-visibility threshold is crossed.
                return RepaintBoundary(
                  child: CustomPaint(
                    size: size,
                    painter: _SchematicPainter(
                      lines: lines,
                      stationPoints: points,
                      stationNames: {for (final s in bundle.stations) s.stopId: s.name},
                      interchangeIds: interchanges,
                      overlay: overlay,
                      labelScale: viewScale,
                      labelColor: scheme.onSurface,
                      haloColor: scheme.surface,
                      stationFill: scheme.surface,
                      stationBorder: scheme.onSurface.withValues(alpha: 0.55),
                      textPainterCache: _tpCache,
                    ),
                  ),
                );
              },
            ),
          ),
        );
      },
    );
  }

  _RouteOverlay _buildOverlay(
    JourneyPlan plan,
    Map<String, Station> byId,
    Map<String, Offset> points,
  ) {
    final stopIds = <String>{plan.origin.stopId, plan.destination.stopId};
    final highlightLines = <_LinePolyline>[];
    for (final leg in plan.legs) {
      final legStops = leg.stations ?? [leg.board, leg.alight];
      for (final stop in legStops) {
        stopIds.add(stop.stopId);
      }
      if (!leg.isRide) continue;
      final polyline = [
        for (final stop in legStops)
          if (points[stop.stopId] != null) points[stop.stopId]!,
      ];
      if (polyline.length < 2) continue;
      highlightLines.add(_LinePolyline(
        color: routeColor(leg.routeColor, leg.routeLongName),
        points: polyline,
      ));
    }
    return _RouteOverlay(
      stopIds: stopIds,
      boardStopId: plan.origin.stopId,
      alightStopId: plan.destination.stopId,
      interchangeStopIds: plan.interchangeStopIds.toSet(),
      lines: highlightLines,
    );
  }

  void _onCanvasTap(Offset local, Map<String, Offset> points, {double hitRadius = 22}) {
    String? nearest;
    var nearestDistance = double.infinity;
    points.forEach((stopId, point) {
      final distance = (point - local).distance;
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearest = stopId;
      }
    });
    // A generous but not sloppy hit radius, in canvas (unscaled) pixels —
    // the design-space asset canvas passes a proportionally larger radius.
    if (nearest == null || nearestDistance > hitRadius) return;
    final station = ref.read(stationIndexProvider)[nearest];
    if (station == null) return;

    // Reach mode intercepts the tap entirely: it fetches an isochrone from the
    // tapped station and never touches the plan/origin/destination state, so
    // toggling back off leaves tap-to-plan exactly as it was.
    if (_reachMode) {
      _fetchReach(station);
      return;
    }

    setState(() {
      if (_origin == null) {
        _origin = station;
      } else if (_destination == null && station.stopId != _origin!.stopId) {
        _destination = station;
      } else {
        // Both set (or the same station tapped twice) — start a new pick.
        _origin = station;
        _destination = null;
        _plan = null;
        _error = null;
      }
    });
    if (_origin != null && _destination != null) _planJourney();
  }

  Future<void> _pick({required bool isOrigin}) async {
    final station = await showAppBottomSheet<Station>(
      context,
      builder: (_) => StationSearchSheet(
        title: isOrigin ? 'Where from?' : 'Where to?',
        isOrigin: isOrigin,
      ),
    );
    if (station == null) return;
    setState(() {
      if (isOrigin) {
        _origin = station;
      } else {
        _destination = station;
      }
      _plan = null;
      _error = null;
    });
    if (_origin != null && _destination != null) await _planJourney();
  }

  void _swap() {
    setState(() {
      final origin = _origin;
      _origin = _destination;
      _destination = origin;
      _plan = null;
      _error = null;
    });
    _planJourney();
  }

  void _clearPlan() {
    setState(() {
      _plan = null;
      _origin = null;
      _destination = null;
      _error = null;
    });
  }

  Future<void> _planJourney() async {
    if (_origin == null || _destination == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final plan = await ref
          .read(journeyRepositoryProvider)
          .plan(_origin!.stopId, _destination!.stopId);
      if (!mounted) return;
      setState(() => _plan = plan);
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() {
        _error = isConnectivityError(error)
            ? "You're offline — we can't plan a trip without a connection right now."
            : "We couldn't find a route between these stations.";
      });
    } on Exception {
      if (!mounted) return;
      setState(() => _error = "We couldn't find a route between these stations.");
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Flip reachability mode. Turning it off clears every reach field so the
  /// painter reverts to null and the plan map is byte-for-byte its old self.
  void _toggleReach() {
    setState(() {
      _reachMode = !_reachMode;
      if (!_reachMode) {
        _reachOrigin = null;
        _reachMinutes = null;
        _error = null;
      }
    });
  }

  /// Fetch the timetable isochrone from [station] and tint the map by it.
  /// Tapping a different station simply re-runs this. The repository swallows
  /// transport errors into an empty map, so an empty result is surfaced as a
  /// gentle caption rather than an exception.
  Future<void> _fetchReach(Station station) async {
    setState(() {
      _reachOrigin = station.stopId;
      _loading = true;
      _error = null;
    });
    try {
      final minutes = await ref.read(journeyRepositoryProvider).reach(station.stopId);
      if (!mounted) return;
      setState(() {
        _reachMinutes = minutes.isEmpty ? null : minutes;
        if (minutes.isEmpty) {
          _error = "We couldn't load reach times from ${station.name} right now.";
        }
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }
}

// -- overlay + polyline models ------------------------------------------------

/// One drawable line: a colour and its projected canvas points.
class _LinePolyline {
  const _LinePolyline({required this.color, required this.points});

  final Color color;
  final List<Offset> points;
}

/// The highlighted-route state layered over the base diagram.
class _RouteOverlay {
  const _RouteOverlay({
    required this.stopIds,
    required this.boardStopId,
    required this.alightStopId,
    required this.interchangeStopIds,
    required this.lines,
  });

  final Set<String> stopIds;
  final String boardStopId;
  final String alightStopId;
  final Set<String> interchangeStopIds;
  final List<_LinePolyline> lines;
}

// -- affine geo fit -------------------------------------------------------------

/// A least-squares affine map (lat, lon) -> design-space (x, y), fitted from
/// stations present in both the bundle and the schematic asset. Used only to
/// place bundle stations the asset does not know about (feed additions newer
/// than the asset), so they still appear in roughly the right spot.
class _AffineGeoFit {
  const _AffineGeoFit(this.a, this.b, this.c, this.d, this.e, this.f);

  // x = a*lon + b*lat + c;  y = d*lon + e*lat + f
  final double a, b, c, d, e, f;

  static _AffineGeoFit? fromStations(List<Station> common, NetworkSchematic schematic) {
    if (common.length < 3) return null;
    // Normal equations for the basis [lon, lat, 1]: M * params = rhs, where
    // M is the 3x3 Gram matrix shared by the x and y solves.
    double m00 = 0, m01 = 0, m02 = 0, m11 = 0, m12 = 0, m22 = 0;
    double rx0 = 0, rx1 = 0, rx2 = 0, ry0 = 0, ry1 = 0, ry2 = 0;
    for (final station in common) {
      final p = schematic.positionOf(station.stopId);
      if (p == null) continue;
      final lon = station.lon;
      final lat = station.lat;
      m00 += lon * lon;
      m01 += lon * lat;
      m02 += lon;
      m11 += lat * lat;
      m12 += lat;
      m22 += 1;
      rx0 += lon * p.dx;
      rx1 += lat * p.dx;
      rx2 += p.dx;
      ry0 += lon * p.dy;
      ry1 += lat * p.dy;
      ry2 += p.dy;
    }
    final det = m00 * (m11 * m22 - m12 * m12) -
        m01 * (m01 * m22 - m12 * m02) +
        m02 * (m01 * m12 - m11 * m02);
    // Collinear (or too few) reference stations make the fit degenerate; the
    // caller then simply leaves the unknown stations undrawn.
    if (!det.isFinite || det.abs() < 1e-9) return null;
    double solve0(double r0, double r1, double r2) =>
        (r0 * (m11 * m22 - m12 * m12) -
            m01 * (r1 * m22 - m12 * r2) +
            m02 * (r1 * m12 - m11 * r2)) /
        det;
    double solve1(double r0, double r1, double r2) =>
        (m00 * (r1 * m22 - r2 * m12) -
            r0 * (m01 * m22 - m12 * m02) +
            m02 * (m01 * r2 - r1 * m02)) /
        det;
    double solve2(double r0, double r1, double r2) =>
        (m00 * (m11 * r2 - m12 * r1) -
            m01 * (m01 * r2 - m02 * r1) +
            r0 * (m01 * m12 - m11 * m02)) /
        det;
    return _AffineGeoFit(
      solve0(rx0, rx1, rx2),
      solve1(rx0, rx1, rx2),
      solve2(rx0, rx1, rx2),
      solve0(ry0, ry1, ry2),
      solve1(ry0, ry1, ry2),
      solve2(ry0, ry1, ry2),
    );
  }

  Offset apply(double lat, double lon) =>
      Offset(a * lon + b * lat + c, d * lon + e * lat + f);
}

// -- painter ------------------------------------------------------------------

class _SchematicPainter extends CustomPainter {
  _SchematicPainter({
    required this.lines,
    required this.stationPoints,
    required this.stationNames,
    required this.interchangeIds,
    required this.overlay,
    required this.labelScale,
    required this.labelColor,
    required this.haloColor,
    required this.stationFill,
    required this.stationBorder,
    required this.textPainterCache,
  });

  final List<_LinePolyline> lines;
  final Map<String, Offset> stationPoints;
  final Map<String, String> stationNames;
  final Set<String> interchangeIds;
  final _RouteOverlay? overlay;
  final double labelScale;
  final Color labelColor;
  final Color haloColor;
  final Color stationFill;
  final Color stationBorder;

  /// Owned by the State (it outlives every painter instance), so laid-out
  /// label text survives across repaints and painter reconstructions. Keys
  /// fold in the colour, so a theme change misses to fresh entries instead of
  /// painting stale colours.
  final Map<String, TextPainter> textPainterCache;

  static const double _dimLine = 0.16;
  static const double _dimDot = 0.20;

  @override
  void paint(Canvas canvas, Size size) {
    final hasOverlay = overlay != null;

    // 1. Base line geometry. When a route is highlighted, everything else
    //    dims — exactly how DMRC greys out the rest of the network.
    for (final line in lines) {
      final opacity = hasOverlay ? _dimLine : 0.9;
      _drawPolyline(canvas, line.points, line.color.withValues(alpha: opacity), 4.5);
    }

    // 2. Highlighted route legs, drawn bold on top.
    if (hasOverlay) {
      for (final line in overlay!.lines) {
        _drawPolyline(canvas, line.points, line.color, 7);
      }
    }

    // 3. Station dots.
    final dotFill = Paint()..style = PaintingStyle.fill;
    final dotStroke = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;
    stationPoints.forEach((stopId, point) {
      final onRoute = !hasOverlay || overlay!.stopIds.contains(stopId);
      final isInterchange = interchangeIds.contains(stopId);
      final alpha = onRoute ? 1.0 : _dimDot;

      if (isInterchange) {
        // A white-filled ring — the universal "you can change lines here" mark.
        dotFill.color = stationFill.withValues(alpha: alpha);
        dotStroke.color = stationBorder.withValues(alpha: alpha);
        dotStroke.strokeWidth = 2;
        canvas.drawCircle(point, 6, dotFill);
        canvas.drawCircle(point, 6, dotStroke);
      } else {
        // Ordinary stations stay small and light so the zoomed-out whole
        // network view reads as lines with ticks, not a field of rings.
        dotFill.color = stationFill.withValues(alpha: alpha);
        dotStroke.color = stationBorder.withValues(alpha: alpha);
        dotStroke.strokeWidth = 1.2;
        canvas.drawCircle(point, 2.5, dotFill);
        canvas.drawCircle(point, 2.5, dotStroke);
      }
    });

    // 4. Board / alight endpoints of the highlighted route, marked distinctly.
    if (hasOverlay) {
      _drawEndpoint(canvas, overlay!.boardStopId, AppColors.success, 'A');
      _drawEndpoint(canvas, overlay!.alightStopId, AppColors.danger, 'B');
    }

    // 5. Labels. Zoom buckets decide *eligibility* (interchanges and route
    //    endpoints always eligible; on-route stations from labelScale 1.4;
    //    everything else from 2.3), then a greedy declutter pass resolves
    //    collisions among the eligible: labels are placed in priority order
    //    (endpoints, then interchanges, then the rest) and any label whose
    //    box overlaps an already-placed one is skipped entirely.
    final endpointLabels = <(String, Offset, double)>[];
    final interchangeLabels = <(String, Offset, double)>[];
    final ordinaryLabels = <(String, Offset, double)>[];
    stationPoints.forEach((stopId, point) {
      final onRoute = !hasOverlay || overlay!.stopIds.contains(stopId);
      final isInterchange = interchangeIds.contains(stopId);
      final isEndpoint = hasOverlay &&
          (stopId == overlay!.boardStopId || stopId == overlay!.alightStopId);
      final zoomedEnough = labelScale >= 2.3;
      final routeZoom = hasOverlay && onRoute && labelScale >= 1.4;
      final show = isEndpoint || isInterchange || zoomedEnough || routeZoom;
      if (!show) return;
      if (hasOverlay && !onRoute && !zoomedEnough) return;
      final entry = (stopId, point, onRoute ? 1.0 : 0.5);
      if (isEndpoint) {
        endpointLabels.add(entry);
      } else if (isInterchange) {
        interchangeLabels.add(entry);
      } else {
        ordinaryLabels.add(entry);
      }
    });
    // Overlap is tested in canvas space. InteractiveViewer scales the whole
    // canvas uniformly (positions and the fixed-canvas-size font together),
    // and a uniform scale preserves rect overlap — so canvas-space overlap IS
    // screen-space overlap, at every zoom level, with no scale compensation.
    final placed = <Rect>[];
    for (final labels in [endpointLabels, interchangeLabels, ordinaryLabels]) {
      for (final (stopId, point, opacity) in labels) {
        _drawLabel(canvas, point, stopId, stationNames[stopId] ?? '', opacity, placed);
      }
    }
  }

  void _drawPolyline(Canvas canvas, List<Offset> points, Color color, double width) {
    if (points.length < 2) return;
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = width
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final path = Path()..moveTo(points.first.dx, points.first.dy);
    for (var i = 1; i < points.length; i++) {
      path.lineTo(points[i].dx, points[i].dy);
    }
    canvas.drawPath(path, paint);
  }

  void _drawEndpoint(Canvas canvas, String stopId, Color color, String letter) {
    final point = stationPoints[stopId];
    if (point == null) return;
    canvas.drawCircle(point, 9, Paint()..color = Colors.white);
    canvas.drawCircle(point, 8, Paint()..color = color);
    final tp = TextPainter(
      text: TextSpan(
        text: letter,
        style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, point - Offset(tp.width / 2, tp.height / 2));
  }

  /// Draws one station label, unless its box collides with a label already
  /// placed this frame (greedy declutter — higher-priority labels were drawn
  /// first, so the loser is simply skipped).
  ///
  /// The halo is a stroked pass of the same text under the fill — the cheap
  /// standard technique. The old blur-Shadow halo made every label one of the
  /// most expensive things on the canvas.
  void _drawLabel(
    Canvas canvas,
    Offset point,
    String stopId,
    String text,
    double opacity,
    List<Rect> placed,
  ) {
    if (text.isEmpty) return;
    final fill = _labelPainter(stopId, text, opacity, halo: false);
    final origin = point + const Offset(8, -6);
    final rect = (origin & Size(fill.width, fill.height)).inflate(2);
    for (final other in placed) {
      if (rect.overlaps(other)) return;
    }
    placed.add(rect);
    _labelPainter(stopId, text, opacity, halo: true).paint(canvas, origin);
    fill.paint(canvas, origin);
  }

  /// A cached, already-laid-out painter for one label variant. Keyed by stop,
  /// halo/fill, opacity AND colour — the colour in the key is what keeps a
  /// theme change from ever painting stale colours (see the cache owner's
  /// comment in _NetworkMapScreenState).
  TextPainter _labelPainter(
    String stopId,
    String text,
    double opacity, {
    required bool halo,
  }) {
    final color = halo ? haloColor : labelColor;
    final key = '$stopId/${halo ? 'halo' : 'fill'}/$opacity/${color.toARGB32()}';
    return textPainterCache.putIfAbsent(key, () {
      final style = halo
          ? TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              foreground: Paint()
                ..style = PaintingStyle.stroke
                ..strokeWidth = 2.5
                ..color = color.withValues(alpha: opacity),
            )
          : TextStyle(
              color: color.withValues(alpha: opacity),
              fontSize: 10,
              fontWeight: FontWeight.w600,
            );
      return TextPainter(
        text: TextSpan(text: text, style: style),
        textDirection: TextDirection.ltr,
        maxLines: 1,
        ellipsis: '…',
      )..layout(maxWidth: 120);
    });
  }

  @override
  bool shouldRepaint(_SchematicPainter old) {
    return old.overlay != overlay ||
        // Any theme-dependent colour change must repaint, not just the label.
        old.labelColor != labelColor ||
        old.haloColor != haloColor ||
        old.stationFill != stationFill ||
        old.stationBorder != stationBorder ||
        // Only repaint on a zoom change that could cross a label threshold.
        _labelBucket(old.labelScale) != _labelBucket(labelScale) ||
        old.lines != lines;
  }

  int _labelBucket(double scale) {
    if (scale >= 2.3) return 2;
    if (scale >= 1.4) return 1;
    return 0;
  }
}

// -- asset-schematic painter ----------------------------------------------------

/// Draws the precomputed octilinear schematic: coloured bands with rounded
/// bends, station beads, classic double-ring interchanges, and every label
/// exactly where the layout tool placed it (anchor + optional -45 rotation).
/// No zoom-bucket gating and no greedy declutter on this path — placement is
/// collision-free by construction, so labels are simply always drawn. The
/// only runtime-placed labels are "extra" stations the asset predates, which
/// go through a small greedy pass against the fixed asset labels.
class _AssetSchematicPainter extends CustomPainter {
  _AssetSchematicPainter({
    required this.lines,
    required this.stations,
    required this.extraPoints,
    required this.extraNames,
    required this.stationPoints,
    required this.overlay,
    required this.labelColor,
    required this.haloColor,
    required this.stationFill,
    required this.stationBorder,
    required this.textPainterCache,
    this.reachMinutes,
    this.reachOrigin,
    this.dark = false,
  });

  final List<_LinePolyline> lines;
  final Map<String, SchematicStation> stations;

  /// Bundle stations the asset does not know, affine-placed at build time.
  final Map<String, Offset> extraPoints;
  final Map<String, String> extraNames;

  /// Every station position (asset + extras) — endpoint markers key off this.
  final Map<String, Offset> stationPoints;
  final _RouteOverlay? overlay;
  final Color labelColor;
  final Color haloColor;
  final Color stationFill;
  final Color stationBorder;

  /// Reachability tint. Null (the default, and always so when reach mode is
  /// off) means "draw dots exactly as before": the tinting branch is skipped
  /// entirely, so the normal map is untouched. When non-null, every station
  /// dot is filled by [reachBucketColor] of its minutes-from-origin, and the
  /// [reachOrigin] dot gets a distinct emphasis ring.
  final Map<String, int>? reachMinutes;
  final String? reachOrigin;
  final bool dark;

  /// Owned by the State — see _SchematicPainter's cache notes. Keys are
  /// namespaced ('a/…') so asset-sized entries never collide with the
  /// geographic fallback painter's 10px entries.
  final Map<String, TextPainter> textPainterCache;

  static const double _dimLine = 0.16;
  static const double _dimDot = 0.20;
  static const double _dimLabel = 0.45;
  static const double _lineWidth = 7;
  static const double _dotRadius = 4;
  static const double _interchangeRadius = 7;

  /// Must stay in step with the layout tool's collision metrics (it measures
  /// text at 11.1px and boxes 14px tall) — a larger font here would overflow
  /// the tool's zero-overlap guarantee.
  static const double _fontSize = 11;

  @override
  void paint(Canvas canvas, Size size) {
    final hasOverlay = overlay != null;

    // 1. Base bands; the rest of the network dims when a route is highlighted.
    for (final line in lines) {
      final opacity = hasOverlay ? _dimLine : 1.0;
      _drawPolyline(canvas, line.points, line.color.withValues(alpha: opacity), _lineWidth);
    }

    // 2. Highlighted route legs, bold, following the same drawn bends.
    if (hasOverlay) {
      for (final line in overlay!.lines) {
        _drawPolyline(canvas, line.points, line.color, _lineWidth + 2);
      }
    }

    // 3. Station marks.
    final dotFill = Paint()..style = PaintingStyle.fill;
    final dotStroke = Paint()..style = PaintingStyle.stroke;
    stations.forEach((stopId, station) {
      final onRoute = !hasOverlay || overlay!.stopIds.contains(stopId);
      _drawMark(canvas, station.position, station.interchange, onRoute, dotFill,
          dotStroke, _reachTintFor(stopId));
    });
    extraPoints.forEach((stopId, point) {
      final onRoute = !hasOverlay || overlay!.stopIds.contains(stopId);
      _drawMark(canvas, point, false, onRoute, dotFill, dotStroke, _reachTintFor(stopId));
    });
    // The origin's emphasis ring is drawn last so it sits above every dot.
    if (reachMinutes != null && reachOrigin != null) {
      final originPoint = stationPoints[reachOrigin];
      if (originPoint != null) {
        _drawReachOriginRing(canvas, originPoint,
            stations[reachOrigin]?.interchange ?? false);
      }
    }

    // 4. A/B endpoints of the highlighted route.
    if (hasOverlay) {
      _drawEndpoint(canvas, overlay!.boardStopId, AppColors.success, 'A');
      _drawEndpoint(canvas, overlay!.alightStopId, AppColors.danger, 'B');
    }

    // 5. Labels: all asset labels, always. Collision rects are only collected
    //    when extras exist — the common case pays nothing for declutter.
    final placed = extraPoints.isEmpty ? null : <Rect>[];
    stations.forEach((stopId, station) {
      final onRoute = !hasOverlay || overlay!.stopIds.contains(stopId);
      _drawAssetLabel(canvas, stopId, station, onRoute ? 1.0 : _dimLabel, placed);
    });
    if (placed != null) {
      extraPoints.forEach((stopId, point) {
        final onRoute = !hasOverlay || overlay!.stopIds.contains(stopId);
        _drawExtraLabel(
            canvas, point, stopId, extraNames[stopId] ?? '', onRoute ? 1.0 : _dimLabel, placed);
      });
    }
  }

  /// The bucket colour for a station in reach mode, or null when reach mode is
  /// off or the station has no known reach time (so it draws as an ordinary,
  /// untinted dot).
  Color? _reachTintFor(String stopId) {
    final minutes = reachMinutes?[stopId];
    if (minutes == null) return null;
    return reachBucketColor(minutes, dark: dark);
  }

  /// A distinct double emphasis ring around the reach origin so the picked
  /// station reads as the source, not just another green (0-minute) dot.
  void _drawReachOriginRing(Canvas canvas, Offset point, bool interchange) {
    final r = (interchange ? _interchangeRadius : _dotRadius) + 4;
    canvas.drawCircle(point, r, Paint()..color = haloColor);
    canvas.drawCircle(
      point,
      r,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.5
        ..color = labelColor,
    );
  }

  void _drawMark(
    Canvas canvas,
    Offset point,
    bool interchange,
    bool onRoute,
    Paint fill,
    Paint stroke,
    Color? reachTint,
  ) {
    // In reach mode the dot is filled by its time bucket at full strength
    // (overlay dimming doesn't apply — reach mode has no highlighted route),
    // with the border kept for definition against same-hue neighbours.
    if (reachTint != null) {
      fill.color = reachTint;
      stroke.color = stationBorder.withValues(alpha: 0.65);
      if (interchange) {
        stroke.strokeWidth = 2;
        canvas.drawCircle(point, _interchangeRadius, fill);
        canvas.drawCircle(point, _interchangeRadius, stroke);
      } else {
        stroke.strokeWidth = 1.4;
        canvas.drawCircle(point, _dotRadius, fill);
        canvas.drawCircle(point, _dotRadius, stroke);
      }
      return;
    }
    final alpha = onRoute ? 1.0 : _dimDot;
    fill.color = stationFill.withValues(alpha: alpha);
    stroke.color = stationBorder.withValues(alpha: alpha);
    if (interchange) {
      // The classic interchange mark: a larger white-filled double ring.
      stroke.strokeWidth = 2;
      canvas.drawCircle(point, _interchangeRadius, fill);
      canvas.drawCircle(point, _interchangeRadius, stroke);
      stroke.strokeWidth = 1.4;
      canvas.drawCircle(point, _interchangeRadius - 3.2, stroke);
    } else {
      stroke.strokeWidth = 1.4;
      canvas.drawCircle(point, _dotRadius, fill);
      canvas.drawCircle(point, _dotRadius, stroke);
    }
  }

  void _drawPolyline(Canvas canvas, List<Offset> points, Color color, double width) {
    if (points.length < 2) return;
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = width
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    final path = Path()..moveTo(points.first.dx, points.first.dy);
    for (var i = 1; i < points.length; i++) {
      path.lineTo(points[i].dx, points[i].dy);
    }
    canvas.drawPath(path, paint);
  }

  void _drawEndpoint(Canvas canvas, String stopId, Color color, String letter) {
    final point = stationPoints[stopId];
    if (point == null) return;
    canvas.drawCircle(point, 14, Paint()..color = Colors.white);
    canvas.drawCircle(point, 12.5, Paint()..color = color);
    final tp = TextPainter(
      text: TextSpan(
        text: letter,
        style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.w800),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, point - Offset(tp.width / 2, tp.height / 2));
  }

  /// The label's top-left corner relative to the station dot, per the asset's
  /// anchor: 'e' sits 6px right of the dot edge vertically centred, 'w' is
  /// mirrored, 'n'/'s' sit above/below horizontally centred, corners diagonal.
  Offset _anchorLocal(SchematicLabelAnchor anchor, double dotRadius, double w, double h) {
    const gap = 6.0;
    final d = dotRadius + gap;
    final diag = d * 0.78;
    return switch (anchor) {
      SchematicLabelAnchor.e => Offset(d, -h / 2),
      SchematicLabelAnchor.w => Offset(-d - w, -h / 2),
      SchematicLabelAnchor.n => Offset(-w / 2, -d - h),
      SchematicLabelAnchor.s => Offset(-w / 2, d),
      SchematicLabelAnchor.ne => Offset(diag, -diag - h),
      SchematicLabelAnchor.nw => Offset(-diag - w, -diag - h),
      SchematicLabelAnchor.se => Offset(diag, diag),
      SchematicLabelAnchor.sw => Offset(-diag - w, diag),
    };
  }

  /// The layout tool collision-checks label boxes of this height (design px);
  /// text is vertically centred inside so tool geometry and paint agree.
  static const double _labelBoxH = 14;

  void _drawAssetLabel(
    Canvas canvas,
    String stopId,
    SchematicStation station,
    double opacity,
    List<Rect>? placed,
  ) {
    if (station.label.isEmpty) return;
    final fill = _labelPainter(stopId, station.label, opacity, halo: false,
        bold: station.interchange);
    final halo = _labelPainter(stopId, station.label, opacity, halo: true,
        bold: station.interchange);

    // Preferred path: the tool's exact collision-checked box origin. For
    // angle 0 it is the box's top-left; for -45 it is the rotation pivot
    // (the box corner where the text begins, reading up-right).
    final dx = station.labelDx;
    final dy = station.labelDy;
    if (dx != null && dy != null) {
      final centering = Offset(0, (_labelBoxH - fill.height) / 2);
      if (station.labelAngle != 0) {
        canvas.save();
        canvas.translate(station.x + dx, station.y + dy);
        canvas.rotate(station.labelAngle * math.pi / 180);
        halo.paint(canvas, centering);
        fill.paint(canvas, centering);
        canvas.restore();
        final reach = (fill.width + fill.height) * 0.72;
        placed?.add(Rect.fromLTWH(station.x + dx, station.y + dy - reach, reach, reach));
      } else {
        final origin = Offset(station.x + dx, station.y + dy) + centering;
        halo.paint(canvas, origin);
        fill.paint(canvas, origin);
        placed?.add((origin & Size(fill.width, fill.height)).inflate(2));
      }
      return;
    }

    // Legacy path (assets without labelDx/labelDy): anchor-derived offset.
    final dotRadius = station.interchange ? _interchangeRadius : _dotRadius;
    final local = _anchorLocal(station.labelAnchor, dotRadius, fill.width, fill.height);
    if (station.labelAngle != 0) {
      canvas.save();
      canvas.translate(station.x, station.y);
      canvas.rotate(station.labelAngle * math.pi / 180);
      halo.paint(canvas, local);
      fill.paint(canvas, local);
      canvas.restore();
      // Conservative unrotated bound, good enough to keep runtime-placed
      // extra labels from sitting on top of a rotated one.
      final reach = (fill.width + fill.height) * 0.72;
      placed?.add(Rect.fromLTWH(station.x, station.y - reach, reach, reach));
    } else {
      final origin = station.position + local;
      halo.paint(canvas, origin);
      fill.paint(canvas, origin);
      placed?.add((origin & Size(fill.width, fill.height)).inflate(2));
    }
  }

  /// Runtime-placed label for a station the asset predates: same greedy
  /// skip-on-overlap rule the geographic path uses, seeded with every asset
  /// label's rect so extras never overprint the designed layout.
  void _drawExtraLabel(
    Canvas canvas,
    Offset point,
    String stopId,
    String text,
    double opacity,
    List<Rect> placed,
  ) {
    if (text.isEmpty) return;
    final fill = _labelPainter(stopId, text, opacity, halo: false, bold: false);
    final origin = point + const Offset(10, -8);
    final rect = (origin & Size(fill.width, fill.height)).inflate(2);
    for (final other in placed) {
      if (rect.overlaps(other)) return;
    }
    placed.add(rect);
    _labelPainter(stopId, text, opacity, halo: true, bold: false).paint(canvas, origin);
    fill.paint(canvas, origin);
  }

  TextPainter _labelPainter(
    String stopId,
    String text,
    double opacity, {
    required bool halo,
    required bool bold,
  }) {
    final color = halo ? haloColor : labelColor;
    final weight = bold ? FontWeight.w700 : FontWeight.w600;
    final key = 'a/$stopId/${halo ? 'halo' : 'fill'}/$opacity/${color.toARGB32()}/$bold';
    return textPainterCache.putIfAbsent(key, () {
      // Explicit family: Android's default is Roboto anyway, and naming it
      // lets the render-preview test load a real font under this family
      // (flutter_test otherwise renders every glyph as an Ahem block).
      final style = halo
          ? TextStyle(
              fontSize: _fontSize,
              fontFamily: 'Roboto',
              fontWeight: weight,
              foreground: Paint()
                ..style = PaintingStyle.stroke
                ..strokeWidth = 3
                ..color = color.withValues(alpha: opacity),
            )
          : TextStyle(
              color: color.withValues(alpha: opacity),
              fontSize: _fontSize,
              fontFamily: 'Roboto',
              fontWeight: weight,
            );
      return TextPainter(
        text: TextSpan(text: text, style: style),
        textDirection: TextDirection.ltr,
        maxLines: 1,
        ellipsis: '…',
      )..layout(maxWidth: 240);
    });
  }

  @override
  bool shouldRepaint(_AssetSchematicPainter old) {
    return old.overlay != overlay ||
        old.labelColor != labelColor ||
        old.haloColor != haloColor ||
        old.stationFill != stationFill ||
        old.stationBorder != stationBorder ||
        !identical(old.stations, stations) ||
        old.lines != lines ||
        old.extraPoints != extraPoints ||
        // A new reach map is a fresh instance each fetch, so identity is the
        // right, allocation-free trigger; origin/dark cover re-tinting in place
        // and a theme flip. All three are inert (null/false) when reach is off.
        !identical(old.reachMinutes, reachMinutes) ||
        old.reachOrigin != reachOrigin ||
        old.dark != dark;
  }
}

// -- line legend ----------------------------------------------------------------

/// A compact, horizontally scrollable legend: one colour-dot chip per drawn
/// lineKey (branches deduplicated), docked under the endpoint bar.
class _LineLegend extends StatelessWidget {
  const _LineLegend({required this.lines});

  final List<SchematicLine> lines;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final seen = <String>{};
    final entries = <(String, Color)>[];
    for (final line in lines) {
      if (line.lineKey.isEmpty || !seen.add(line.lineKey)) continue;
      entries.add((_prettyName(line.lineKey), routeColor(line.color, line.lineKey)));
    }
    if (entries.isEmpty) return const SizedBox.shrink();
    return SizedBox(
      height: 32,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: entries.length,
        separatorBuilder: (_, __) => const SizedBox(width: AppSpacing.sm),
        itemBuilder: (context, index) {
          final (name, color) = entries[index];
          return GlassSurface(
            blur: true,
            borderRadius: AppRadius.pillR,
            padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                ),
                const SizedBox(width: AppSpacing.xs),
                Text(name, style: theme.textTheme.labelMedium),
              ],
            ),
          );
        },
      ),
    );
  }

  /// 'RED' -> 'Red' — the lineKey is already the human line name, just shouty.
  String _prettyName(String key) =>
      key.length < 2 ? key : key[0].toUpperCase() + key.substring(1).toLowerCase();
}

// -- top endpoint bar ---------------------------------------------------------

class _EndpointBar extends StatelessWidget {
  const _EndpointBar({
    required this.origin,
    required this.destination,
    required this.onPickOrigin,
    required this.onPickDestination,
    required this.onSwap,
    required this.reachMode,
    required this.onToggleReach,
  });

  final Station? origin;
  final Station? destination;
  final VoidCallback onPickOrigin;
  final VoidCallback onPickDestination;
  final VoidCallback? onSwap;
  final bool reachMode;
  final VoidCallback onToggleReach;

  @override
  Widget build(BuildContext context) {
    return GlassSurface(
      blur: true,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
      child: Row(
        children: [
          Expanded(
            child: Column(
              children: [
                _EndpointField(
                  icon: Icons.trip_origin_rounded,
                  label: 'From',
                  station: origin,
                  onTap: onPickOrigin,
                ),
                const Divider(height: 1),
                _EndpointField(
                  icon: Icons.flag_rounded,
                  label: 'To',
                  station: destination,
                  onTap: onPickDestination,
                ),
              ],
            ),
          ),
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconPillButton(
                icon: Icons.hub_rounded,
                tooltip: reachMode ? 'Reach mode on — tap a station' : 'Reach: how far is everywhere?',
                filled: reachMode,
                onPressed: onToggleReach,
              ),
              const SizedBox(height: AppSpacing.xs),
              IconPillButton(
                icon: Icons.swap_vert_rounded,
                tooltip: 'Swap From and To',
                onPressed: onSwap,
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// The reach-mode caption + bucket legend, shown only while reach mode is on.
/// Before a station is picked it prompts; once an isochrone is loaded it names
/// the origin and shows the colour buckets so the tinted dots read as minutes.
class _ReachOverlayBar extends StatelessWidget {
  const _ReachOverlayBar({required this.originName, required this.showLegend});

  final String? originName;
  final bool showLegend;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dark = theme.brightness == Brightness.dark;
    final caption = originName == null
        ? 'Reach mode: tap any station to see how far everywhere is.'
        : 'Fastest timetable times from $originName';
    return GlassSurface(
      blur: true,
      borderRadius: AppRadius.lgR,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(caption, style: theme.textTheme.labelMedium),
          if (showLegend) ...[
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.md,
              runSpacing: AppSpacing.xs,
              children: [
                for (final (label, color) in reachLegend(dark: dark))
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 10,
                        height: 10,
                        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                      ),
                      const SizedBox(width: AppSpacing.xs),
                      Text(label, style: theme.textTheme.labelSmall),
                    ],
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _EndpointField extends StatelessWidget {
  const _EndpointField({
    required this.icon,
    required this.label,
    required this.station,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final Station? station;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return InkWell(
      onTap: onTap,
      borderRadius: AppRadius.mdR,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: AppSpacing.sm),
        child: Row(
          children: [
            Icon(icon, size: 18, color: theme.colorScheme.onSurfaceVariant),
            const SizedBox(width: AppSpacing.md),
            Expanded(
              child: Text(
                station?.name ?? 'Choose $label station',
                style: station == null
                    ? theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)
                    : theme.textTheme.titleSmall,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            Icon(Icons.chevron_right_rounded, size: 18, color: theme.colorScheme.onSurfaceVariant),
          ],
        ),
      ),
    );
  }
}

class _LoadingPill extends StatelessWidget {
  const _LoadingPill();

  @override
  Widget build(BuildContext context) {
    return GlassSurface(
      blur: true,
      borderRadius: AppRadius.pillR,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
          const SizedBox(width: AppSpacing.md),
          Text('Finding the best route…', style: Theme.of(context).textTheme.labelMedium),
        ],
      ),
    );
  }
}

class _ErrorPill extends StatelessWidget {
  const _ErrorPill({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return GlassSurface(
      blur: true,
      color: AppColors.danger.withValues(alpha: 0.14),
      borderRadius: AppRadius.lgR,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg, vertical: AppSpacing.md),
      child: Text(
        message,
        style: TextStyle(color: Theme.of(context).colorScheme.error),
      ),
    );
  }
}

// -- journey result panel -----------------------------------------------------

/// The DMRC-style breakdown, in a draggable bottom panel: totals up top, then
/// each ride leg (line, direction, board -> alight, time, expandable station
/// list) with interchange markers between them.
class _JourneyPanel extends StatelessWidget {
  const _JourneyPanel({required this.plan, required this.onClear});

  final JourneyPlan plan;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return DraggableScrollableSheet(
      initialChildSize: 0.42,
      minChildSize: 0.16,
      maxChildSize: 0.9,
      snap: true,
      snapSizes: const [0.16, 0.42, 0.9],
      builder: (context, scrollController) {
        return DecoratedBox(
          decoration: BoxDecoration(
            color: scheme.surfaceContainerHighest,
            borderRadius: const BorderRadius.vertical(top: Radius.circular(AppRadius.xxl)),
            border: Border(top: BorderSide(color: scheme.outlineVariant)),
          ),
          child: ClipRRect(
            borderRadius: const BorderRadius.vertical(top: Radius.circular(AppRadius.xxl)),
            child: ListView(
              controller: scrollController,
              padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.md, AppSpacing.lg, AppSpacing.xxl),
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    margin: const EdgeInsets.only(bottom: AppSpacing.md),
                    decoration: BoxDecoration(
                      color: scheme.outlineVariant,
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
                _PanelHeader(plan: plan, onClear: onClear),
                const SizedBox(height: AppSpacing.lg),
                ..._buildLegs(context),
                const SizedBox(height: AppSpacing.md),
                GhostButton(
                  label: 'Buy ticket for this trip',
                  icon: Icons.confirmation_number_rounded,
                  expand: true,
                  onPressed: () => context.push('/tickets'),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  List<Widget> _buildLegs(BuildContext context) {
    final widgets = <Widget>[];
    JourneyLeg? previousRide;
    for (final leg in plan.legs) {
      if (leg.isRide) {
        // A change is a boarding that follows an earlier ride — never the very
        // first boarding, whose wait is just the initial platform wait.
        if (previousRide != null) {
          widgets.add(_InterchangeRow(atStation: leg.board.name, waitSeconds: leg.waitSeconds));
        }
        widgets.add(_LegCard(leg: leg));
        previousRide = leg;
      } else {
        widgets.add(_WalkRow(leg: leg));
      }
      widgets.add(const SizedBox(height: AppSpacing.sm));
    }
    return widgets;
  }
}

class _PanelHeader extends StatelessWidget {
  const _PanelHeader({required this.plan, required this.onClear});

  final JourneyPlan plan;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final fare = estimateFare(plan);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('ESTIMATED TRAVEL TIME', style: theme.textTheme.labelSmall),
                  Text(minutesLabel(plan.expectedTravelSeconds),
                      style: theme.textTheme.displaySmall),
                ],
              ),
            ),
            IconPillButton(
              icon: Icons.close_rounded,
              tooltip: 'Clear route',
              onPressed: onClear,
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: [
            _Stat(label: 'Arrive', value: clockTime(plan.expectedArrivalAt)),
            _Stat(label: 'Fare (est.)', value: '₹${fare.rupees}'),
            _Stat(label: 'Stations', value: '${plan.remainingStations.length}'),
            _Stat(label: 'Changes', value: '${plan.interchangeCount}'),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        Text(
          'Times and fare are estimates from the published schedule, not a live gate charge.',
          style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.outline),
        ),
      ],
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md, vertical: AppSpacing.sm),
      decoration: BoxDecoration(
        color: theme.colorScheme.surfaceContainer,
        borderRadius: AppRadius.mdR,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label.toUpperCase(), style: theme.textTheme.labelSmall),
          Text(value, style: theme.textTheme.titleMedium),
        ],
      ),
    );
  }
}

/// One ride leg, DMRC-style: the line, its direction ("towards <terminus>"),
/// board -> alight, the leg's time, and an expandable full station list.
class _LegCard extends StatefulWidget {
  const _LegCard({required this.leg});

  final JourneyLeg leg;

  @override
  State<_LegCard> createState() => _LegCardState();
}

class _LegCardState extends State<_LegCard> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final leg = widget.leg;
    final stations = leg.stations ?? const <JourneyStop>[];
    // Intermediate stops (everything between board and alight).
    final between = stations.length > 2 ? stations.sublist(1, stations.length - 1) : const <JourneyStop>[];

    return GlassSurface(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LineChip(label: cleanLineName(leg.routeLongName), colorHex: leg.routeColor),
          if (leg.platformHint != null && leg.platformHint!.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.sm),
            Row(
              children: [
                Icon(Icons.navigation_rounded, size: 14, color: theme.colorScheme.onSurfaceVariant),
                const SizedBox(width: AppSpacing.xs),
                Expanded(
                  child: Text(_towardsLabel(leg.platformHint!),
                      style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
                ),
              ],
            ),
          ],
          const SizedBox(height: AppSpacing.md),
          _StationRow(icon: Icons.trip_origin_rounded, label: leg.board.name, bold: true),
          const _StationRow(icon: Icons.south_rounded, label: '', muted: true),
          _StationRow(icon: Icons.place_rounded, label: leg.alight.name, bold: true),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              Text(
                '${stopsLabel((stations.isEmpty ? 1 : stations.length) - 1)} · ${minutesLabel(leg.seconds)}',
                style: theme.textTheme.bodySmall,
              ),
              const Spacer(),
              if (between.isNotEmpty)
                TextButton(
                  onPressed: () => setState(() => _expanded = !_expanded),
                  child: Text(_expanded ? 'Hide stations' : 'Show ${between.length} stations'),
                ),
            ],
          ),
          if (_expanded && between.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final stop in between)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Row(
                        children: [
                          Icon(Icons.circle, size: 6, color: theme.colorScheme.outline),
                          const SizedBox(width: AppSpacing.sm),
                          Expanded(child: Text(stop.name, style: theme.textTheme.bodyMedium)),
                        ],
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _StationRow extends StatelessWidget {
  const _StationRow({required this.icon, required this.label, this.bold = false, this.muted = false});

  final IconData icon;
  final String label;
  final bool bold;
  final bool muted;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(icon, size: 16, color: muted ? theme.colorScheme.outline : theme.colorScheme.onSurface),
          const SizedBox(width: AppSpacing.md),
          if (label.isNotEmpty)
            Expanded(
              child: Text(
                label,
                style: bold ? theme.textTheme.titleSmall : theme.textTheme.bodyMedium,
              ),
            ),
        ],
      ),
    );
  }
}

class _InterchangeRow extends StatelessWidget {
  const _InterchangeRow({required this.atStation, this.waitSeconds});

  final String atStation;
  final double? waitSeconds;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final wait = (waitSeconds ?? 0) > 0 ? ' · wait about ${minutesLabel(waitSeconds)}' : '';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Icon(Icons.transfer_within_a_station_rounded, size: 18, color: theme.colorScheme.primary),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text('Change at $atStation$wait',
                style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.primary)),
          ),
        ],
      ),
    );
  }
}

class _WalkRow extends StatelessWidget {
  const _WalkRow({required this.leg});

  final JourneyLeg leg;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Icon(Icons.directions_walk_rounded, size: 18, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: AppSpacing.md),
          Expanded(
            child: Text(
              'Walk to ${leg.alight.name} · ${distanceLabel(leg.distanceM)} · about ${minutesLabel(leg.seconds)}',
              style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}

/// The GTFS headsign (leg.platformHint) is usually a bare terminus name
/// ("Rithala"), which we prefix with "Towards". But the backend's fallback
/// headsign is already "Towards <terminus>" when a trip has no trip_headsign,
/// so guard against a doubled prefix.
String _towardsLabel(String headsign) {
  final trimmed = headsign.trim();
  return trimmed.toLowerCase().startsWith('towards')
      ? trimmed
      : 'Towards $trimmed';
}

/// Builds the asset-schematic painter exactly as the screen does, with fixed
/// light-theme colors and no journey overlay — used by the render-preview
/// test to rasterize the real asset and eyeball it, since the painter class
/// itself is private to this library.
@visibleForTesting
Widget buildSchematicPreviewForTest(NetworkSchematic schematic) {
  return CustomPaint(
    size: schematic.canvas,
    painter: _AssetSchematicPainter(
      lines: [
        for (final line in schematic.lines)
          if (line.points.length >= 2)
            _LinePolyline(
              color: routeColor(line.color, line.lineKey),
              points: line.points,
            ),
      ],
      stations: schematic.stations,
      extraPoints: const {},
      extraNames: const {},
      stationPoints: {
        for (final entry in schematic.stations.entries) entry.key: entry.value.position,
      },
      overlay: null,
      labelColor: const Color(0xFF111111),
      haloColor: const Color(0xFFFAFAF7),
      stationFill: const Color(0xFFFFFFFF),
      stationBorder: const Color(0xBF111111),
      textPainterCache: <String, TextPainter>{},
    ),
  );
}
