import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/features/map/train_animator.dart';

void main() {
  test('new trains appear in place without tweening from origin', () {
    final animator = TrainAnimator(onFrame: (_) {});
    animator.applyPositions({'v1': (28.60, 77.00)});
    final train = animator.trains['v1']!;
    expect(train.lat, 28.60);
    expect(train.lon, 77.00);
    expect(train.settled, isTrue);
    animator.dispose();
  });

  test('retargeted trains interpolate towards the new position', () {
    final animator = TrainAnimator(onFrame: (_) {});
    animator.applyPositions({'v1': (28.60, 77.00)});
    animator.applyPositions({'v1': (28.60, 77.02)});
    final train = animator.trains['v1']!;
    expect(train.settled, isFalse);

    train.advance(0.5);
    expect(train.lon, closeTo(77.01, 1e-9));
    train.advance(0.5);
    expect(train.lon, closeTo(77.02, 1e-9));
    expect(train.settled, isTrue);
    animator.dispose();
  });

  test('removed trains disappear from the animated set', () {
    final animator = TrainAnimator(onFrame: (_) {});
    animator.applyPositions({'v1': (28.6, 77.0), 'v2': (28.6, 77.01)});
    animator.applyPositions({'v1': (28.6, 77.0)});
    expect(animator.trains.keys, ['v1']);
    animator.dispose();
  });

  test('ticker fires frames until every train settles', () async {
    var frames = 0;
    final animator = TrainAnimator(
      onFrame: (_) => frames += 1,
      duration: const Duration(milliseconds: 200),
      fps: 20,
    );
    animator.applyPositions({'v1': (28.60, 77.00)});
    animator.applyPositions({'v1': (28.60, 77.02)});
    await Future<void>.delayed(const Duration(milliseconds: 400));
    expect(frames, greaterThan(2));
    expect(animator.trains['v1']!.settled, isTrue);
    final settledFrames = frames;
    await Future<void>.delayed(const Duration(milliseconds: 200));
    expect(frames, settledFrames, reason: 'ticker stops when nothing moves');
    animator.dispose();
  });
}
