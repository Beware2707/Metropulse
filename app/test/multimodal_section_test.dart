// The multimodal leg chain: compact, and free of internal keys.
//
// '448DOWN' is DTS's internal route id — the DOWN suffix is a direction key,
// meaningless to a rider (the same honesty rule as never showing route_id).
import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/features/planner/journey_planner_screen.dart';

void main() {
  test('leg chain reads like a journey, not like a database', () {
    final chain = multimodalLegChainForTest(<String, dynamic>{
      'legs': [
        {'kind': 'walk', 'minutes': 7},
        {'kind': 'bus', 'agency': 'DTC', 'route': '448DOWN'},
        {'kind': 'walk', 'minutes': 1},
        {'kind': 'metro', 'agency': 'DMRC', 'route': 'YELLOW'},
      ],
    });
    expect(chain, 'walk 7 min → DTC 448 → walk 1 min → Yellow Line');
    expect(chain.contains('DOWN'), isFalse,
        reason: 'direction suffixes are internal keys, not rider information');
  });

  test('UP suffix and unknown kinds survive sanely', () {
    final chain = multimodalLegChainForTest(<String, dynamic>{
      'legs': [
        {'kind': 'bus', 'agency': 'DIMTS', 'route': '974UP'},
        {'kind': 'ferry'},
      ],
    });
    expect(chain, 'DIMTS 974 → ferry');
  });
}
