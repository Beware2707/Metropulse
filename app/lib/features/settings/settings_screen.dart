import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart' show favouriteStationsProvider;
import '../search/search_providers.dart' show recentSearchIdsProvider;
import 'settings_providers.dart';

/// Settings: appearance (dark mode, dynamic colour), accessibility (text
/// size, high contrast), notifications, backend, offline storage, privacy
/// and about.
class SettingsScreen extends ConsumerWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeMode = ref.watch(themeModeProvider);
    final apiBase = ref.watch(apiBaseProvider);
    final bundle = ref.watch(offlineBundleProvider).valueOrNull;
    final highContrast = ref.watch(highContrastProvider);
    final dynamicColorEnabled = ref.watch(dynamicColorEnabledProvider);
    final textScale = ref.watch(textScaleFactorProvider);
    final notificationsEnabled = ref.watch(notificationsEnabledProvider);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Appearance', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                RadioGroup<ThemeMode>(
                  groupValue: themeMode,
                  onChanged: (selected) {
                    if (selected != null) {
                      ref.read(themeModeProvider.notifier).setMode(selected);
                    }
                  },
                  child: Column(
                    children: [
                      for (final (mode, label, icon) in [
                        (ThemeMode.system, 'System', Icons.brightness_auto),
                        (ThemeMode.light, 'Light', Icons.light_mode_outlined),
                        (ThemeMode.dark, 'Dark', Icons.dark_mode_outlined),
                      ])
                        RadioListTile<ThemeMode>(
                          value: mode,
                          secondary: Icon(icon),
                          title: Text(label),
                        ),
                    ],
                  ),
                ),
                SwitchListTile(
                  secondary: const Icon(Icons.wallpaper_outlined),
                  title: const Text('Dynamic colour'),
                  subtitle: const Text('Match your device wallpaper theme, where supported'),
                  value: dynamicColorEnabled,
                  onChanged: (value) async {
                    await ref.read(localStoreProvider).setDynamicColorEnabled(value);
                    ref.invalidate(dynamicColorEnabledProvider);
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text('Accessibility', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                SwitchListTile(
                  secondary: const Icon(Icons.contrast),
                  title: const Text('High contrast'),
                  subtitle: const Text('Increases colour contrast throughout the app'),
                  value: highContrast,
                  onChanged: (value) async {
                    await ref.read(localStoreProvider).setHighContrast(value);
                    ref.invalidate(highContrastProvider);
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.text_fields),
                  title: const Text('Text size'),
                  subtitle: Slider(
                    value: textScale,
                    min: 0.85,
                    max: 1.6,
                    divisions: 15,
                    label: '${(textScale * 100).round()}%',
                    onChanged: (value) async {
                      await ref.read(localStoreProvider).saveTextScaleFactor(value);
                      ref.invalidate(textScaleFactorProvider);
                    },
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text('Notifications', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                SwitchListTile(
                  secondary: const Icon(Icons.notifications_active_outlined),
                  title: const Text('Alerts and reminders'),
                  subtitle: const Text(
                    'Destination, interchange, last-train, leave-home and '
                    'service alerts',
                  ),
                  value: notificationsEnabled,
                  onChanged: (value) async {
                    await ref.read(localStoreProvider).setNotificationsEnabled(value);
                    ref.invalidate(notificationsEnabledProvider);
                  },
                ),
                ListTile(
                  leading: const Icon(Icons.inbox_outlined),
                  title: const Text('View all notifications'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => context.push('/notifications'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text('Backend', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.dns_outlined),
              title: const Text('API server'),
              subtitle: Text(apiBase),
              trailing: const Icon(Icons.edit_outlined),
              onTap: () => _editApiBase(context, ref),
            ),
          ),
          const SizedBox(height: 16),
          Text('Offline data', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: const Icon(Icons.offline_pin_outlined),
                  title: Text(bundle == null
                      ? 'Not downloaded'
                      : '${bundle.stations.length} stations · '
                          '${bundle.routes.length} lines cached'),
                  subtitle:
                      bundle == null ? null : Text('Dataset version ${bundle.version}'),
                  trailing: IconButton(
                    icon: const Icon(Icons.refresh),
                    onPressed: () => ref.invalidate(offlineBundleProvider),
                  ),
                ),
                ListTile(
                  leading: const Icon(Icons.delete_outline),
                  title: const Text('Clear cached history and searches'),
                  subtitle: const Text(
                    'Removes cached favourites, journey history and recent '
                    'searches (station data is kept)',
                  ),
                  onTap: () => _confirmClearCache(context, ref),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text('Privacy', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          const Card(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Text(
                'MetroPulse identifies your device with an anonymous token — '
                'no name, email or phone number is collected. Your location '
                'is used only on this device to find nearby stations and is '
                'never sent to the server. Favourites, journeys and '
                'notifications are stored against your anonymous account so '
                'they sync across app restarts.',
              ),
            ),
          ),
          const SizedBox(height: 16),
          Text('About', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          const Card(
            child: ListTile(
              leading: Icon(Icons.info_outline),
              title: Text('MetroPulse'),
              subtitle: Text('Version ${AppConfig.appVersion}'),
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
      ref.invalidate(apiBaseProvider);
      // Rebuild the whole dependency graph on the new base URL.
      ref.invalidate(apiClientProvider);
    }
  }

  Future<void> _confirmClearCache(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Clear cached data?'),
        content: const Text(
          'This removes cached favourites, journey history and recent '
          'searches on this device. Nothing is deleted from your account.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Clear'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final store = ref.read(localStoreProvider);
    await Future.wait([
      store.clearRecentSearches(),
      store.saveFavouriteStationsCache(const []),
      store.saveJourneyHistoryCache(const []),
    ]);
    ref
      ..invalidate(favouriteStationsProvider)
      ..invalidate(recentSearchIdsProvider);
    if (context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('Cache cleared.')));
    }
  }
}
