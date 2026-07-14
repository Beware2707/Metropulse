// Pins the pure AQI -> (label, severity colour) mapping to the standard US
// EPA bands, sampled one value inside each band. No network, no widget.
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/data/air_quality_service.dart';

void main() {
  test('each US AQI band maps to its honest label', () {
    expect(aqiSeverity(40).label, 'Good air today'); // 0-50 good
    expect(aqiSeverity(75).label, 'Moderate air today'); // 51-100 moderate
    expect(aqiSeverity(125).label, 'Poor for sensitive groups'); // 101-150 USG
    expect(aqiSeverity(175).label, 'Unhealthy air today'); // 151-200 unhealthy
    expect(aqiSeverity(250).label, 'Very poor air today'); // 201-300 very unhealthy
    expect(aqiSeverity(350).label, 'Hazardous air today'); // 301+ hazardous
  });

  test('band boundaries are lower-band inclusive', () {
    expect(aqiSeverity(50).label, 'Good air today');
    expect(aqiSeverity(51).label, 'Moderate air today');
    expect(aqiSeverity(100).label, 'Moderate air today');
    expect(aqiSeverity(101).label, 'Poor for sensitive groups');
    expect(aqiSeverity(150).label, 'Poor for sensitive groups');
    expect(aqiSeverity(151).label, 'Unhealthy air today');
    expect(aqiSeverity(200).label, 'Unhealthy air today');
    expect(aqiSeverity(201).label, 'Very poor air today');
    expect(aqiSeverity(300).label, 'Very poor air today');
    expect(aqiSeverity(301).label, 'Hazardous air today');
  });

  test('severity colours escalate distinctly across the six bands', () {
    final colors = [40, 75, 125, 175, 250, 350].map((a) => aqiSeverity(a).color).toSet();
    expect(colors.length, 6);
  });

  test('undergroundSharePercent counts only known-elevation stations', () {
    // b elevated (above), c/d underground (elevated == false), e unknown.
    final facilities = <String, bool?>{
      'b': true,
      'c': false,
      'd': false,
      'e': null,
    };
    // Route a,b,c,d,e: a missing, e unknown -> 3 known, 2 underground -> 67%.
    expect(undergroundSharePercent(['a', 'b', 'c', 'd', 'e'], facilities), 67);
    // No known station along the route -> null, not a fake 0%.
    expect(undergroundSharePercent(['a', 'e'], facilities), isNull);
    // Empty facilities -> null.
    expect(undergroundSharePercent(['a', 'b'], const {}), isNull);
  });
}
