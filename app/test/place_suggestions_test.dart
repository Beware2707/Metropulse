import 'package:flutter_test/flutter_test.dart';
import 'package:metropulse_app/domain/models/intelligence.dart';
import 'package:metropulse_app/domain/place_suggestions.dart';

InferredPlace _home({String stopId = 'S1', String stopName = 'Alpha'}) => InferredPlace(
      stopId: stopId,
      stopName: stopName,
      role: 'home',
      confidence: 1.0,
      sampleSize: 10,
      rationale: 'the station you start from most often (10 trips)',
    );

InferredPlace _anchor({String stopId = 'S4', String stopName = 'Delta'}) => InferredPlace(
      stopId: stopId,
      stopName: stopName,
      role: 'weekday_anchor',
      confidence: 1.0,
      sampleSize: 8,
      rationale: 'where you most often head on weekdays from your home station (8 trips)',
    );

void main() {
  test('suggests Home when nothing is tagged Home yet', () {
    final suggestions = placeSuggestions([], [_home()]);
    expect(suggestions, hasLength(1));
    expect(suggestions.single.labelOptions, ['Home']);
  });

  test('does not suggest Home when a favourite is already labelled Home', () {
    final rows = [
      {'stop_id': 'S9', 'label': 'Home'},
    ];
    expect(placeSuggestions(rows, [_home()]), isEmpty);
  });

  test('label matching is case-insensitive', () {
    final rows = [
      {'stop_id': 'S9', 'label': 'home'},
    ];
    expect(placeSuggestions(rows, [_home()]), isEmpty);
  });

  test(
    'never suggests a place that is already a favourite under any label — '
    'accepting a suggestion must only ever add, never silently relabel',
    () {
      final rows = [
        {'stop_id': 'S1', 'label': 'Gym'},
      ];
      expect(placeSuggestions(rows, [_home()]), isEmpty);
    },
  );

  test('a weekday anchor offers both Work and College — never guesses which', () {
    final suggestions = placeSuggestions([], [_anchor()]);
    expect(suggestions, hasLength(1));
    expect(suggestions.single.labelOptions, ['Work', 'College']);
  });

  test('does not suggest a weekday anchor when Work is already tagged', () {
    final rows = [
      {'stop_id': 'S9', 'label': 'Work'},
    ];
    expect(placeSuggestions(rows, [_anchor()]), isEmpty);
  });

  test('does not suggest a weekday anchor when College is already tagged', () {
    final rows = [
      {'stop_id': 'S9', 'label': 'College'},
    ];
    expect(placeSuggestions(rows, [_anchor()]), isEmpty);
  });

  test('can surface both Home and weekday-anchor suggestions together', () {
    final suggestions = placeSuggestions([], [_home(), _anchor()]);
    expect(suggestions.map((s) => s.place.role), ['home', 'weekday_anchor']);
  });

  test('empty inference and empty favourites yields no suggestions', () {
    expect(placeSuggestions([], []), isEmpty);
  });
}
