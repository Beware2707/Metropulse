import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/core_providers.dart';

/// Settings: dark mode, backend URL, offline cache state.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);
    final store = ref.watch(localStoreProvider);
    final bundle = ref.watch(offlineBundleProvider).valueOrNull;

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Appearance', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                for (final (mode, label, icon) in [
                  (ThemeMode.system, 'System', Icons.brightness_auto),
                  (ThemeMode.light, 'Light', Icons.light_mode_outlined),
                  (ThemeMode.dark, 'Dark', Icons.dark_mode_outlined),
                ])
                  RadioListTile<ThemeMode>(
                    value: mode,
                    groupValue: themeMode,
                    secondary: Icon(icon),
                    title: Text(label),
                    onChanged: (selected) {
                      if (selected != null) {
                        ref.read(themeModeProvider.notifier).setMode(selected);
                      }
                    },
                  ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text('Backend', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.dns_outlined),
              title: const Text('API server'),
              subtitle: Text(store.apiBase),
              trailing: const Icon(Icons.edit_outlined),
              onTap: () => _editApiBase(context, ref),
            ),
          ),
          const SizedBox(height: 16),
          Text('Offline data', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.offline_pin_outlined),
              title: Text(bundle == null
                  ? 'Not downloaded'
                  : '${bundle.stations.length} stations · '
                      '${bundle.routes.length} lines cached'),
              subtitle: bundle == null
                  ? null
                  : Text('Dataset version ${bundle.version}'),
              trailing: IconButton(
                icon: const Icon(Icons.refresh),
                onPressed: () => ref.invalidate(offlineBundleProvider),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _editApiBase(BuildContext context, WidgetRef ref) async {
    final store = ref.read(localStoreProvider);
    final controller = TextEditingController(text: store.apiBase);
    final result = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('API server'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.url,
          decoration: const InputDecoration(hintText: 'http://host:8000'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () =>
                Navigator.of(dialogContext).pop(controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (result != null && result.isNotEmpty) {
      await store.saveApiBase(result);
      // Rebuild the whole dependency graph on the new base URL.
      ref.invalidate(apiClientProvider);
    }
  }
}
