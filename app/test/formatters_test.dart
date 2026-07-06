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

  group('cleanLineName', () {
    test('splits DMRC\'s "<CODE>_<origin> to <destination>" convention into a real line name', () {
      expect(cleanLineName('ORANGE/AIRPORT_Dwarka Sector - 21 to New Delhi'), 'Airport Express Line');
      expect(cleanLineName('RED_Rithala to Dilshad Garden'), 'Red Line');
      expect(cleanLineName('YELLOW_Huda City Centre to Samaypur Badli'), 'Yellow Line');
      expect(cleanLineName('VIOLET_Kashmere Gate to Raja Nahar Singh'), 'Violet Line');
      expect(cleanLineName('GRAY_Dwarka to Dhansa Bus Stand'), 'Grey Line');
    });

    test('a bare single-letter short code (e.g. route_short_name "O_DN") is ambiguous and left as-is '
        '-- every real display site prefers route_long_name, which always carries the full word', () {
      expect(cleanLineName('O_DN'), 'O_DN');
    });

    test('a name that is already clean passes through unchanged', () {
      expect(cleanLineName('Blue Line'), 'Blue Line');
    });

    test('falls back honestly when nothing is recognisable', () {
      expect(cleanLineName(null), 'Unknown line');
      expect(cleanLineName(''), 'Unknown line');
      expect(cleanLineName('Some Unrecognised Line'), 'Some Unrecognised Line');
    });
  });

  group('routeDescription', () {
    test('extracts the origin-to-destination half of a raw route name', () {
      expect(
        routeDescription('ORANGE/AIRPORT_New Delhi to Dwarka Sector - 21'),
        'New Delhi to Dwarka Sector - 21',
      );
    });

    test('collapses double spaces from the raw feed', () {
      expect(routeDescription('RED_Dilshad Garden  to Rithala'), 'Dilshad Garden to Rithala');
    });

    test('is null when the raw value has no underscore convention to split', () {
      expect(routeDescription('Blue Line'), isNull);
      expect(routeDescription(null), isNull);
    });
  });
}
