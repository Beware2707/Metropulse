import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/core/formatters.dart';

void main() {
  test('minutesLabel renders commuter-friendly durations', () {
    expect(minutesLabel(null), '–');
    expect(minutesLabel(20), 'now');
    expect(minutesLabel(120), '2 min');
    expect(minutesLabel(1920), '32 min');
    expect(minutesLabel(3900), '1 h 05 min');
  });

  test('distanceLabel switches to km past 1000 m', () {
    expect(distanceLabel(null), '–');
    expect(distanceLabel(350), '350 m');
    expect(distanceLabel(1240), '1.2 km');
  });

  test('clockTime tolerates null', () {
    expect(clockTime(null), '–');
  });
}
