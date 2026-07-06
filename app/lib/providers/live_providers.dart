import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/config.dart';
import '../data/ws_client.dart';
import '../domain/models/train.dart';
import '../domain/models/ws_message.dart';
import 'core_providers.dart';

/// The single app-wide WebSocket connection.
final wsClientProvider = Provider<LiveWsClient>((ref) {
  final apiBase = ref.watch(apiClientProvider).apiBase;
  final client = LiveWsClient(url: AppConfig.wsUrlFor(apiBase))..connect();
  ref.onDispose(client.dispose);
  return client;
});

final wsStatusProvider = StreamProvider<WsStatus>(
  (ref) => ref.watch(wsClientProvider).status,
);

/// In-flight service alerts surfaced as banners.
final serviceAlertBannerProvider = StreamProvider<WsAlert>(
  (ref) => ref
      .watch(wsClientProvider)
      .messages
      .where((message) => message is WsAlert)
      .cast<WsAlert>(),
);

/// The live train table, maintained purely from WS snapshots + diffs.
final liveTrainsProvider = NotifierProvider<LiveTrainsNotifier, Map<String, Train>>(
  LiveTrainsNotifier.new,
);

class LiveTrainsNotifier extends Notifier<Map<String, Train>> {
  @override
  Map<String, Train> build() {
    final subscription =
        ref.watch(wsClientProvider).messages.listen(_onMessage);
    ref.onDispose(subscription.cancel);
    return const {};
  }

  void _onMessage(WsMessage message) {
    switch (message) {
      case WsSnapshot(:final trains):
        state = {for (final train in trains) train.id: train};
      case WsUpdate(:final added, :final moved, :final removed):
        final next = Map<String, Train>.of(state);
        for (final train in added) {
          next[train.id] = train;
        }
        for (final train in moved) {
          next[train.id] = train;
        }
        for (final id in removed) {
          next.remove(id);
        }
        state = next;
      case WsAlert() || WsHeartbeat():
        break;
    }
  }
}

/// One live train by id (rebuilds only when that train changes).
final liveTrainProvider = Provider.family<Train?, String>(
  (ref, vehicleId) => ref.watch(
    liveTrainsProvider.select((trains) => trains[vehicleId]),
  ),
);

/// Live trains whose next stop is the given station (arrivals board).
///
/// Full ETA-seconds sorting isn't practical here without restructuring this
/// provider into an async aggregate: per-train ETA is a separate repository
/// call (`trainsRepositoryProvider().eta(vehicleId)`), not a field already
/// present on [Train], so this provider can't read it synchronously. As a
/// minimal, non-invasive improvement, trains already `atStation` (soonest to
/// depart) are surfaced first; ties fall back to the previous alphabetical
/// order by line name.
final arrivalsForStationProvider = Provider.family<List<Train>, String>(
  (ref, stopId) {
    final trains = ref.watch(liveTrainsProvider).values.where(
          (train) => train.nextStation?.stopId == stopId && !train.isStale,
        );
    return trains.toList()
      ..sort((a, b) {
        if (a.atStation != b.atStation) {
          return a.atStation ? -1 : 1;
        }
        return a.lineLabel.compareTo(b.lineLabel);
      });
  },
);
