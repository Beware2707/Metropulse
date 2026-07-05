import 'dart:async';
import 'dart:ui' show lerpDouble;

/// A train's animated position between two GTFS updates.
class AnimatedTrain {
  AnimatedTrain({required this.lat, required this.lon})
      : _fromLat = lat,
        _fromLon = lon,
        _toLat = lat,
        _toLon = lon;

  double lat;
  double lon;
  double _fromLat;
  double _fromLon;
  double _toLat;
  double _toLon;
  double _progress = 1.0;

  void retarget(double newLat, double newLon) {
    _fromLat = lat;
    _fromLon = lon;
    _toLat = newLat;
    _toLon = newLon;
    _progress = 0.0;
  }

  bool get settled => _progress >= 1.0;

  void advance(double step) {
    _progress = (_progress + step).clamp(0.0, 1.0);
    lat = lerpDouble(_fromLat, _toLat, _progress)!;
    lon = lerpDouble(_fromLon, _toLon, _progress)!;
  }
}

/// Tweens every train from its previous to its latest GTFS position over
/// [duration], ticking [onFrame] while any train is still moving.
///
/// Trains glide between updates instead of teleporting. Note the honest
/// division of labour: MapLibre renders on the GPU at the display's native
/// 60/120 Hz; this ticker only feeds it fresh GeoJSON at [fps] — pushing
/// source updates faster than ~20/s wastes platform-channel bandwidth for
/// no visible gain at metro speeds.
class TrainAnimator {
  TrainAnimator({
    required this.onFrame,
    this.duration = const Duration(seconds: 4),
    this.fps = 20,
  });

  final void Function(Map<String, AnimatedTrain> trains) onFrame;
  final Duration duration;
  final int fps;

  final Map<String, AnimatedTrain> _trains = {};
  Timer? _ticker;
  bool _paused = false;

  Map<String, AnimatedTrain> get trains => _trains;

  void applyPositions(Map<String, (double, double)> latest) {
    for (final entry in latest.entries) {
      final existing = _trains[entry.key];
      if (existing == null) {
        // New train: appear in place, no tween from (0, 0).
        _trains[entry.key] =
            AnimatedTrain(lat: entry.value.$1, lon: entry.value.$2);
      } else {
        existing.retarget(entry.value.$1, entry.value.$2);
      }
    }
    _trains.removeWhere((id, _) => !latest.containsKey(id));
    _ensureTicking();
  }

  /// Battery hygiene: stop ticking while the screen is not visible.
  void pause() {
    _paused = true;
    _ticker?.cancel();
    _ticker = null;
  }

  /// Resume after [pause]; trains snap-finish their pending tweens.
  void resume() {
    _paused = false;
    for (final train in _trains.values) {
      train.advance(1.0); // don't replay stale motion after a long pause
    }
    onFrame(_trains);
  }

  void _ensureTicking() {
    if (_ticker != null || _paused) return;
    final interval = Duration(milliseconds: 1000 ~/ fps);
    final step = interval.inMilliseconds / duration.inMilliseconds;
    _ticker = Timer.periodic(interval, (_) {
      var anyMoving = false;
      for (final train in _trains.values) {
        if (!train.settled) {
          train.advance(step);
          anyMoving = true;
        }
      }
      onFrame(_trains);
      if (!anyMoving) {
        _ticker?.cancel();
        _ticker = null;
      }
    });
  }

  void dispose() {
    _ticker?.cancel();
    _ticker = null;
  }
}
