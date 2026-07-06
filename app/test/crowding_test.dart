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

  group('recommendedCoachReasons', () {
    test('null or missing coach data yields no reasons', () {
      expect(recommendedCoachReasons(null), isEmpty);
      expect(recommendedCoachReasons(const {}), isEmpty);
    });

    test('finds the reasons for the recommended coach specifically, not just the first entry', () {
      final coach = {
        'recommended_coach': 3,
        'coaches': [
          {'coach_index': 1, 'reasons': ['typically crowded']},
          {'coach_index': 3, 'reasons': ['typically less crowded', 'short walk to a destination exit']},
        ],
      };
      expect(recommendedCoachReasons(coach), ['typically less crowded', 'short walk to a destination exit']);
    });

    test('an unmatched recommended_coach yields no reasons rather than a wrong one', () {
      final coach = {
        'recommended_coach': 9,
        'coaches': [
          {'coach_index': 1, 'reasons': ['typically crowded']},
        ],
      };
      expect(recommendedCoachReasons(coach), isEmpty);
    });
  });

  group('crowdSource', () {
    test('passes through the honesty label as-is', () {
      expect(crowdSource({'crowd_source': 'observed'}), 'observed');
      expect(crowdSource({'crowd_source': 'prior'}), 'prior');
    });

    test('null coach data yields no source claim', () {
      expect(crowdSource(null), isNull);
    });
  });
}
