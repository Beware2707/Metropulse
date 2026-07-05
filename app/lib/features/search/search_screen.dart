import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../providers/core_providers.dart';

/// Station search over the offline bundle — fully functional without network.
class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});

  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final bundle = ref.watch(offlineBundleProvider);
    final stations = bundle.valueOrNull?.stations ?? const [];
    final query = _query.trim().toLowerCase();
    final matches = query.isEmpty
        ? stations
        : stations
            .where((s) => s.name.toLowerCase().contains(query))
            .toList();

    return Scaffold(
      appBar: AppBar(title: const Text('Search stations')),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: TextField(
              autofocus: true,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search),
                hintText: 'Station name',
                border: OutlineInputBorder(),
              ),
              onChanged: (value) => setState(() => _query = value),
            ),
          ),
          if (bundle.isLoading)
            const Expanded(child: Center(child: CircularProgressIndicator()))
          else if (stations.isEmpty)
            const Expanded(
              child: Center(
                child: Text('Station data not downloaded yet.\n'
                    'Connect once to cache the network for offline use.'),
              ),
            )
          else
            Expanded(
              child: ListView.builder(
                itemCount: matches.length,
                itemBuilder: (_, index) {
                  final station = matches[index];
                  return ListTile(
                    leading: const Icon(Icons.place_outlined),
                    title: Text(station.name),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => context.push('/station/${station.stopId}'),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}
