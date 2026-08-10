// Counting station stops from the phone's accelerometer, for the 63 of 215
// Delhi Metro stations that are underground.
//
// The insight that makes this worth building: you do not need to know WHERE
// you are to know HOW MANY stops you have made. GPS dies in a tunnel because
// satellite signals arrive weaker than the receiver's own noise floor and a
// few metres of concrete ends them. The accelerometer does not care — it is
// measuring the train, not the sky.
//
// A metro train has a distinctive signature: accelerate, cruise, decelerate,
// then sit still at a platform, then repeat. If we know where the rider
// boarded (they told us — they started the journey), counting those cycles
// places them without any radio at all.
//
// The failure mode this must not have: a train HELD between stations also
// looks stopped, and counting that as a station would put the rider one stop
// ahead of reality — worse than no estimate, because they would stand up at
// the wrong platform. Two guards below address it, and neither is perfect,
// which is why this source reports its own decay.

/// One accelerometer reading, reduced to the only thing that matters here.
class MotionSample {
  const MotionSample({required this.magnitude, required this.at});

  /// Magnitude of total acceleration in m/s². At rest this sits near gravity
  /// (~9.8) with very little variation; a moving train adds vibration.
  final double magnitude;
  final DateTime at;
}

/// What the counter currently believes, and how much it should be believed.
class StopCount {
  const StopCount({
    required this.stops,
    required this.isStopped,
    required this.confidence,
  });

  /// Station stops detected since the counter started.
  final int stops;

  /// True while the train is judged to be standing still.
  final bool isStopped;

  /// 1.0 immediately after a confirmed position, decaying with each
  /// unconfirmed stop. Dead reckoning accumulates error; pretending otherwise
  /// is how a helpful estimate becomes a confident wrong answer.
  final double confidence;
}

/// A stop total after the timetable has vetoed the impossible.
class StopCountCheck {
  const StopCountCheck({required this.stops, required this.wasCorrected});

  final int stops;

  /// True when the raw count claimed more stations than the elapsed time
  /// physically allows. Worth surfacing: it means the accelerometer counted
  /// something that was not a platform, so the remaining count deserves less
  /// trust even after correction.
  final bool wasCorrected;
}

/// Detects station stops from a stream of accelerometer samples.
///
/// Deliberately takes samples rather than owning a sensor subscription: the
/// detection rules are the subtle part and they deserve to be testable
/// without a device.
class MotionStopCounter {
  MotionStopCounter({
    this.stillnessThreshold = 0.35,
    this.window = const Duration(seconds: 6),
    this.minimumDwell = const Duration(seconds: 12),
    this.minimumRunTime = const Duration(seconds: 45),
    this.confidenceDecayPerStop = 0.12,
  });

  /// Standard deviation of acceleration magnitude below which the train is
  /// considered still. A stationary train still registers doors, people and
  /// building hum, so this is not near-zero.
  final double stillnessThreshold;

  /// How much history the standard deviation is computed over.
  final Duration window;

  /// A stop shorter than this is a jolt or a signal check, not a station.
  final Duration minimumDwell;

  /// **The guard against counting a mid-tunnel hold as a station.** A real
  /// run between two Delhi Metro stations takes at least this long, so a stop
  /// arriving sooner cannot be the next station — whatever it is, we have not
  /// travelled far enough for it to count.
  final Duration minimumRunTime;

  /// How much certainty each unconfirmed stop costs.
  final double confidenceDecayPerStop;

  final List<MotionSample> _recent = [];
  int _stops = 0;
  bool _stopped = false;
  DateTime? _stoppedSince;
  DateTime? _lastDeparture;
  bool _countedThisStop = false;
  double _confidence = 1.0;

  int get stops => _stops;

  /// Called when a real position confirms where the rider actually is —
  /// resets the accumulated dead-reckoning error.
  void confirmPosition({required int stopsSoFar}) {
    _stops = stopsSoFar;
    _confidence = 1.0;
  }

  /// Feed one sample; returns the current belief.
  StopCount add(MotionSample sample) {
    _recent.add(sample);
    final cutoff = sample.at.subtract(window);
    _recent.removeWhere((s) => s.at.isBefore(cutoff));

    final still = _standardDeviation() < stillnessThreshold;

    if (still && !_stopped) {
      _stopped = true;
      _stoppedSince = sample.at;
      _countedThisStop = false;
    } else if (!still && _stopped) {
      _stopped = false;
      _stoppedSince = null;
      _lastDeparture = sample.at;
    }

    // Count the stop only once it has lasted long enough to be a platform,
    // and only if we actually travelled far enough to have reached one.
    if (_stopped && !_countedThisStop && _stoppedSince != null) {
      final dwell = sample.at.difference(_stoppedSince!);
      final ranLongEnough = _lastDeparture == null ||
          _stoppedSince!.difference(_lastDeparture!) >= minimumRunTime;
      if (dwell >= minimumDwell && ranLongEnough) {
        _stops++;
        _countedThisStop = true;
        _confidence = (_confidence - confidenceDecayPerStop).clamp(0.0, 1.0);
      }
    }

    return StopCount(
      stops: _stops,
      isStopped: _stopped,
      confidence: _confidence,
    );
  }

  double _standardDeviation() {
    // One sample tells you nothing about variation; treat it as moving rather
    // than declaring a stop on no evidence.
    if (_recent.length < 3) return double.infinity;
    final mean =
        _recent.map((s) => s.magnitude).reduce((a, b) => a + b) / _recent.length;
    final variance = _recent
            .map((s) => (s.magnitude - mean) * (s.magnitude - mean))
            .reduce((a, b) => a + b) /
        _recent.length;
    return variance <= 0 ? 0 : _sqrt(variance);
  }

  /// Cross-check a counted stop total against what the timetable makes
  /// physically possible, and correct it downwards when it cannot be true.
  ///
  /// The asymmetry here is the whole point, and it is worth being precise
  /// about because the obvious version of this check does not work:
  ///
  /// **Agreement proves nothing.** A train held mid-tunnel makes the counter
  /// over-count (the hold looks like a platform) AND makes the journey slower,
  /// so a schedule keyed on elapsed time drifts in the same direction. Both
  /// can be wrong by one, together, and still agree.
  ///
  /// **A physical bound does work.** [cumulativeFastestRun] holds the shortest
  /// time in which each station can be reached from the origin. A train cannot
  /// beat that. So a count exceeding what the elapsed time allows is
  /// impossible, and impossible is a fact rather than a guess — that is the
  /// over-count corrected here.
  ///
  /// **Under-counting cannot be caught this way.** Taking much longer than
  /// scheduled is what a delayed train looks like, and also what a missed
  /// short dwell looks like; nothing in the timing separates them. So a count
  /// is never revised upwards — doing so would put a rider a station ahead of
  /// where they are, which is the exact harm this feature exists to prevent.
  static StopCountCheck reconcile({
    required int counted,
    required Duration elapsed,
    required List<Duration> cumulativeFastestRun,
  }) {
    var maxPossible = 0;
    for (final threshold in cumulativeFastestRun) {
      if (elapsed >= threshold) {
        maxPossible++;
      } else {
        break;
      }
    }
    if (counted <= maxPossible) {
      return StopCountCheck(stops: counted, wasCorrected: false);
    }
    return StopCountCheck(stops: maxPossible, wasCorrected: true);
  }

  static double _sqrt(double v) {
    // Newton's method: keeps this file free of a dart:math import so the
    // detection rules stay trivially portable to an isolate.
    var x = v;
    var last = 0.0;
    while ((x - last).abs() > 1e-9) {
      last = x;
      x = 0.5 * (x + v / x);
    }
    return x;
  }
}
