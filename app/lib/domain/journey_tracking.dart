// Next-station tracking from the rider's OWN GPS, with an honest fallback.
//
// The distinction that makes this worth building: MetroPulse has no train
// telemetry, but it can have the rider's position — and where *they* are is a
// real measurement, not an interpolation. Schedule-derived progress drifts
// (a train held at a platform keeps "advancing" on paper), which is exactly
// how somebody misses their stop.
//
// The constraint that shapes every decision below: **63 of 215 Delhi Metro
// stations are underground** (counted from the OTD facilities data). GPS does
// not work in tunnels, and tunnels are concentrated in the central core where
// missing a stop matters most. So this is not a GPS tracker with a fallback
// bolted on; it is a two-source tracker that must say, at every moment, which
// source it is using.
//
// Rules:
//   * A fix is used only if it is recent AND accurate enough. A stale or
//     50-metre-uncertain fix is worse than the schedule, because it looks
//     authoritative.
//   * Losing the fix underground is EXPECTED, not an error. It degrades to
//     schedule silently in behaviour and loudly in labelling.
//   * Progress is monotonic. One stray fix must never rewind the journey and
//     re-announce a station the rider already passed.

import 'nearby.dart' show haversineMeters;

/// Where a tracking update's knowledge came from. Never blended.
enum TrackingSource {
  /// A recent, precise satellite fix from the rider's device.
  gps,

  /// A coarse fix — Android's fused provider falling back to Wi-Fi access
  /// points or cell towers, which DOES work underground where station wifi is
  /// in range. Accuracy is tens to hundreds of metres, so it is only used
  /// when that is still decisive for the station spacing here (see
  /// [JourneyTracker.acceptsFix]). Reported separately because "roughly
  /// where your phone can see wifi" is not "where you are".
  approximate,

  /// Stops counted from the phone's accelerometer since a known station.
  /// The only source that works in a tunnel with no radio at all.
  stopCount,

  /// Interpolated from the timetable — no usable fix and no motion signal.
  schedule,
}

/// One station on the route being tracked.
class TrackedStation {
  const TrackedStation({
    required this.stopId,
    required this.name,
    required this.lat,
    required this.lon,
    this.underground = false,
  });

  final String stopId;
  final String name;
  final double lat;
  final double lon;

  /// True when DMRC's facilities data says this station is below ground.
  /// Used only to explain a missing fix, never to fake one.
  final bool underground;
}

/// A GPS reading, with the two properties that decide whether to trust it.
class RiderFix {
  const RiderFix({
    required this.lat,
    required this.lon,
    required this.accuracyMeters,
    required this.at,
  });

  final double lat;
  final double lon;

  /// Reported horizontal accuracy. Large values mean a cell-tower or wifi
  /// estimate rather than a satellite fix.
  final double accuracyMeters;
  final DateTime at;
}

/// What the rider should be told right now.
class TrackingUpdate {
  const TrackingUpdate({
    required this.nextStation,
    required this.stationsRemaining,
    required this.source,
    required this.isApproaching,
    required this.isFinalStation,
    this.metresToNext,
  });

  final TrackedStation? nextStation;
  final int stationsRemaining;
  final TrackingSource source;

  /// Close enough that the rider should get ready to alight.
  final bool isApproaching;

  /// The next station is their destination.
  final bool isFinalStation;

  /// Straight-line distance to the next station — only ever set when
  /// [source] is [TrackingSource.gps]. A distance derived from a timetable
  /// would be a fabricated precision.
  final double? metresToNext;

  /// One line for the ongoing notification.
  String get headline {
    if (nextStation == null) return 'Journey complete';
    // No colon on the final one: "Get off at: Saket" reads like a form field,
    // and this is the line a rider glances at while standing up.
    return isFinalStation
        ? 'Get off at ${nextStation!.name}'
        : 'Next station: ${nextStation!.name}';
  }

  /// The provenance line. Always shown, because a rider trusting an alert to
  /// tell them when to stand up deserves to know how sure it is.
  String get sourceLabel => switch (source) {
        TrackingSource.gps => metresToNext == null
            ? 'From your location'
            : 'From your location · ${_roundedDistance(metresToNext!)}',
        TrackingSource.approximate => 'From nearby wifi — approximate',
        TrackingSource.stopCount => 'Counted from stops — no signal underground',
        TrackingSource.schedule => 'From the timetable — no GPS signal',
      };
}

String _roundedDistance(double metres) =>
    metres >= 1000 ? '${(metres / 1000).toStringAsFixed(1)} km' : '${metres.round()} m';

/// Tracks one journey, holding the monotonic progress that a single stray fix
/// must not be able to undo.
///
/// Deliberately a class rather than a pure function: "how far along are we"
/// is state, and the guarantee that it never decreases cannot be expressed by
/// a function of the current fix alone.
class JourneyTracker {
  JourneyTracker({
    required this.stations,
    this.arrivalRadiusMetres = 250,
    this.approachRadiusMetres = 800,
    this.maxAccuracyMetres = 150,
    this.maxFixAge = const Duration(seconds: 45),
  });

  /// Ordered origin -> destination.
  final List<TrackedStation> stations;

  /// Within this, treat the rider as AT the station (so the next one becomes
  /// the target). Generous: platforms are long and urban GPS is noisy.
  final double arrivalRadiusMetres;

  /// Within this of the next station, tell them to get ready.
  final double approachRadiusMetres;

  /// Fixes less precise than this are discarded. A 500-metre "fix" in a city
  /// can sit on the wrong line entirely.
  final double maxAccuracyMetres;

  /// Fixes older than this are discarded — a metro train covers a lot of
  /// ground in a minute, so a stale fix is a confident lie.
  final Duration maxFixAge;

  int _reachedIndex = -1;

  /// How many stations the rider has been confirmed past. Exposed for tests
  /// and for restoring a tracker mid-journey.
  int get reachedIndex => _reachedIndex;

  /// Whether a fix is worth using at all, and at what confidence.
  ///
  /// The threshold is ADAPTIVE, because a fixed one throws away the only
  /// positioning that survives a tunnel. Android's fused provider falls back
  /// to wifi access points and cell towers underground and returns a position
  /// with a large accuracy figure. Rejecting everything over ~150 m discards
  /// those — yet if the two nearest stations here are 1.2 km apart, a 300 m
  /// fix still identifies which one you are at beyond doubt.
  ///
  /// So a fix is usable when its uncertainty is comfortably smaller than the
  /// gap it has to resolve. Returns null when the fix cannot be used at all.
  TrackingSource? fixQuality(RiderFix? fix, DateTime now) {
    if (fix == null) return null;
    final age = now.difference(fix.at);
    // A fix timestamped in the future is a broken clock, not a good fix.
    if (age.isNegative || age > maxFixAge) return null;
    if (fix.accuracyMeters <= maxAccuracyMetres) return TrackingSource.gps;
    // Half the local station spacing: at that point the nearest station is
    // still unambiguous even in the worst case of the error ellipse.
    final decisive = _localStationSpacing(fix) / 2;
    if (decisive > 0 && fix.accuracyMeters <= decisive) {
      return TrackingSource.approximate;
    }
    return null;
  }

  /// Distance from the nearest station to its neighbour — the gap a fix has
  /// to be able to resolve, right here rather than network-wide (spacing runs
  /// from a few hundred metres downtown to several km on the outer arms).
  double _localStationSpacing(RiderFix fix) {
    if (stations.length < 2) return 0;
    var nearest = 0;
    var best = double.infinity;
    for (var i = 0; i < stations.length; i++) {
      final d =
          haversineMeters(fix.lat, fix.lon, stations[i].lat, stations[i].lon);
      if (d < best) {
        best = d;
        nearest = i;
      }
    }
    final neighbours = <double>[
      if (nearest > 0)
        haversineMeters(stations[nearest].lat, stations[nearest].lon,
            stations[nearest - 1].lat, stations[nearest - 1].lon),
      if (nearest < stations.length - 1)
        haversineMeters(stations[nearest].lat, stations[nearest].lon,
            stations[nearest + 1].lat, stations[nearest + 1].lon),
    ];
    // The tightest neighbouring gap is the one that must be resolvable.
    return neighbours.isEmpty
        ? 0
        : neighbours.reduce((a, b) => a < b ? a : b);
  }

  /// Kept for callers that only need a yes/no.
  bool acceptsFix(RiderFix? fix, DateTime now) => fixQuality(fix, now) != null;

  /// Fold in the latest fix (or the absence of one) and say what to show.
  ///
  /// [scheduleIndex] is how far the timetable thinks the rider has got — used
  /// only when there is no usable fix, and never allowed to pull progress
  /// backwards either.
  /// [stopsCounted] is the accelerometer's count of station stops since the
  /// journey began — the only signal that survives a tunnel with no radio.
  /// Used when no fix is usable, and still subject to monotonic progress.
  TrackingUpdate update({
    RiderFix? fix,
    required DateTime now,
    int? scheduleIndex,
    int? stopsCounted,
  }) {
    if (stations.isEmpty) {
      return const TrackingUpdate(
        nextStation: null,
        stationsRemaining: 0,
        source: TrackingSource.schedule,
        isApproaching: false,
        isFinalStation: false,
      );
    }

    final quality = fixQuality(fix, now);
    if (quality == null) {
      // No usable fix — underground, indoors, or permission withheld. Prefer
      // counted stops over the timetable: the accelerometer is measuring THIS
      // train, while the schedule is describing an idealised one that never
      // gets held at a platform.
      if (stopsCounted != null && stopsCounted > _reachedIndex) {
        _reachedIndex = stopsCounted.clamp(-1, stations.length - 1);
        return _build(source: TrackingSource.stopCount, metres: null);
      }
      if (scheduleIndex != null && scheduleIndex > _reachedIndex) {
        _reachedIndex = scheduleIndex.clamp(-1, stations.length - 1);
      }
      return _build(
        source: stopsCounted != null
            ? TrackingSource.stopCount
            : TrackingSource.schedule,
        metres: null,
      );
    }

    final position = fix!;
    var nearestIndex = 0;
    var nearestMetres = double.infinity;
    for (var i = 0; i < stations.length; i++) {
      final metres = haversineMeters(
          position.lat, position.lon, stations[i].lat, stations[i].lon);
      if (metres < nearestMetres) {
        nearestMetres = metres;
        nearestIndex = i;
      }
    }

    // Only count a station as reached once we are genuinely at it. Being
    // merely "nearest" to a station is true the whole way between two of them.
    if (nearestMetres <= arrivalRadiusMetres && nearestIndex > _reachedIndex) {
      _reachedIndex = nearestIndex;
    }

    final next = _reachedIndex + 1;
    final metresToNext = next < stations.length
        ? haversineMeters(
            position.lat, position.lon, stations[next].lat, stations[next].lon)
        : null;
    return _build(source: quality, metres: metresToNext);
  }

  TrackingUpdate _build({required TrackingSource source, required double? metres}) {
    final nextIndex = _reachedIndex + 1;
    if (nextIndex >= stations.length) {
      return TrackingUpdate(
        nextStation: null,
        stationsRemaining: 0,
        source: source,
        isApproaching: false,
        isFinalStation: false,
        metresToNext: null,
      );
    }
    return TrackingUpdate(
      nextStation: stations[nextIndex],
      stationsRemaining: stations.length - 1 - _reachedIndex,
      source: source,
      // "Get ready" is a distance claim, so it needs a distance. The timetable
      // cannot support it, and guessing would defeat the point of the feature.
      isApproaching: metres != null && metres <= approachRadiusMetres,
      isFinalStation: nextIndex == stations.length - 1,
      metresToNext: metres,
    );
  }
}
