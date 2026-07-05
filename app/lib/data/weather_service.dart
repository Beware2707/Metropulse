import 'package:dio/dio.dart';

/// Coarse WMO weather-code groupings — just enough to pick a sensible emoji,
/// never precise enough to pretend this is a forecasting product.
enum WeatherCondition { clear, partlyCloudy, cloudy, fog, drizzle, rain, thunderstorm, snow }

class Weather {
  const Weather({required this.temperatureC, required this.condition, required this.isDay});

  final double temperatureC;
  final WeatherCondition condition;
  final bool isDay;

  int get roundedTemperatureC => temperatureC.round();

  /// A day/night-aware icon for the condition — decorative context on the
  /// home greeting, never a substitute for a real weather app.
  String get emoji => switch (condition) {
        WeatherCondition.clear => isDay ? '☀️' : '🌙',
        WeatherCondition.partlyCloudy => isDay ? '🌤️' : '☁️',
        WeatherCondition.cloudy => '☁️',
        WeatherCondition.fog => '🌫️',
        WeatherCondition.drizzle => '🌦️',
        WeatherCondition.rain => '🌧️',
        WeatherCondition.thunderstorm => '⛈️',
        WeatherCondition.snow => '🌨️',
      };
}

/// Thin wrapper over Open-Meteo (free, no API key, no backend involvement —
/// keeping this out of MetroPulse's own API surface entirely).
///
/// Weather is decorative context for the home greeting, not core commute
/// functionality: any failure (offline, blocked, slow) is swallowed here so
/// callers can simply treat it as "nothing to show" rather than an error.
class WeatherService {
  WeatherService()
      : _dio = Dio(
          BaseOptions(
            connectTimeout: const Duration(seconds: 6),
            receiveTimeout: const Duration(seconds: 6),
          ),
        );

  final Dio _dio;

  Future<Weather?> current({required double lat, required double lon}) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>(
        'https://api.open-meteo.com/v1/forecast',
        queryParameters: {
          'latitude': lat,
          'longitude': lon,
          'current': 'temperature_2m,weather_code,is_day',
          'timezone': 'auto',
        },
      );
      final current = response.data?['current'] as Map<String, dynamic>?;
      if (current == null) return null;
      final temperature = (current['temperature_2m'] as num?)?.toDouble();
      final code = (current['weather_code'] as num?)?.toInt();
      if (temperature == null || code == null) return null;
      return Weather(
        temperatureC: temperature,
        condition: conditionForWmoCode(code),
        isDay: current['is_day'] == 1,
      );
    } on Exception {
      return null;
    }
  }
}

/// Maps a WMO weather-interpretation code (the scheme Open-Meteo uses) to a
/// coarse [WeatherCondition]. Pure and standalone so it's unit-testable
/// without any network access.
WeatherCondition conditionForWmoCode(int code) {
  if (code == 0) return WeatherCondition.clear;
  if (code <= 2) return WeatherCondition.partlyCloudy;
  if (code == 3) return WeatherCondition.cloudy;
  if (code == 45 || code == 48) return WeatherCondition.fog;
  if (code >= 51 && code <= 57) return WeatherCondition.drizzle;
  if ((code >= 61 && code <= 67) || (code >= 80 && code <= 82)) return WeatherCondition.rain;
  if (code >= 71 && code <= 77) return WeatherCondition.snow;
  if (code >= 95 && code <= 99) return WeatherCondition.thunderstorm;
  return WeatherCondition.cloudy;
}
