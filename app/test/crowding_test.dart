import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/crowding.dart';

void main() {
  test('null or empty coach data yields no guess', () {
    expect(expectedCrowding(null), isNull);
    expect(expectedCrowding(const []), isNull);
  });

  test('low average occupancy is low', () {
    final coaches = [
      {'occupancy': 0.1},
      {'occupancy': 0.2},
    ];
    expect(expectedCrowding(coaches), 'low');
  });

  test('mid average occupancy is moderate', () {
    final coaches = [
      {'occupancy': 0.5},
      {'occupancy': 0.6},
    ];
    expect(expectedCrowding(coaches), 'moderate');
  });

  test('high average occupancy is high', () {
    final coaches = [
      {'occupancy': 0.8},
      {'occupancy': 0.9},
    ];
    expect(expectedCrowding(coaches), 'high');
  });

  test('matches the documented boundaries exactly (mirrors commute_card.py)', () {
    expect(expectedCrowding([{'occupancy': 0.44}]), 'low');
    expect(expectedCrowding([{'occupancy': 0.45}]), 'moderate');
    expect(expectedCrowding([{'occupancy': 0.69}]), 'moderate');
    expect(expectedCrowding([{'occupancy': 0.70}]), 'high');
  });
}
