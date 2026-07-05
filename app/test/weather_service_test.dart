import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/data/weather_service.dart';

void main() {
  group('conditionForWmoCode', () {
    test('0 is clear sky', () {
      expect(conditionForWmoCode(0), WeatherCondition.clear);
    });

    test('1-2 are partly cloudy', () {
      expect(conditionForWmoCode(1), WeatherCondition.partlyCloudy);
      expect(conditionForWmoCode(2), WeatherCondition.partlyCloudy);
    });

    test('3 is overcast', () {
      expect(conditionForWmoCode(3), WeatherCondition.cloudy);
    });

    test('45/48 are fog', () {
      expect(conditionForWmoCode(45), WeatherCondition.fog);
      expect(conditionForWmoCode(48), WeatherCondition.fog);
    });

    test('51-57 are drizzle', () {
      expect(conditionForWmoCode(51), WeatherCondition.drizzle);
      expect(conditionForWmoCode(57), WeatherCondition.drizzle);
    });

    test('61-67 and 80-82 are rain', () {
      expect(conditionForWmoCode(63), WeatherCondition.rain);
      expect(conditionForWmoCode(81), WeatherCondition.rain);
    });

    test('71-77 are snow', () {
      expect(conditionForWmoCode(73), WeatherCondition.snow);
    });

    test('95+ is thunderstorm', () {
      expect(conditionForWmoCode(95), WeatherCondition.thunderstorm);
      expect(conditionForWmoCode(99), WeatherCondition.thunderstorm);
    });

    test('an unrecognised code falls back to cloudy rather than throwing', () {
      expect(conditionForWmoCode(404), WeatherCondition.cloudy);
    });
  });

  group('Weather.emoji', () {
    test('clear is sun by day, moon by night', () {
      const day = Weather(temperatureC: 30, condition: WeatherCondition.clear, isDay: true);
      const night = Weather(temperatureC: 22, condition: WeatherCondition.clear, isDay: false);
      expect(day.emoji, '☀️');
      expect(night.emoji, '🌙');
    });

    test('roundedTemperatureC rounds to the nearest degree', () {
      const weather = Weather(temperatureC: 27.6, condition: WeatherCondition.clear, isDay: true);
      expect(weather.roundedTemperatureC, 28);
    });
  });
}
