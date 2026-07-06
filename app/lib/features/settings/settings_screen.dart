import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/config.dart';
import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/section_header.dart';
import '../../providers/core_providers.dart';
import '../feedback/feedback_sheet.dart';
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
    final bundleAsync = ref.watch(offlineBundleProvider);
    final bundle = bundleAsync.valueOrNull;
    final bundleLoading = bundleAsync.isLoading;
    final highContrast = ref.watch(highContrastProvider);
    final dynamicColorEnabled = ref.watch(dynamicColorEnabledProvider);
    final textScale = ref.watch(textScaleFactorProvider);
    final notificationsEnabled = ref.watch(notificationsEnabledProvider);

    return Scaffold(
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 140),
            children: [
              Row(
                children: [
                  IconPillButton(icon: Icons.arrow_back_rounded, onPressed: () => context.pop()),
                  const SizedBox(width: AppSpacing.md),
                  Text('Settings', style: Theme.of(context).textTheme.displaySmall),
                ],
              ),
              const SectionHeader(title: 'Appearance'),
              RadioGroup<ThemeMode>(
                groupValue: themeMode,
                onChanged: (selected) {
                  if (selected != null) ref.read(themeModeProvider.notifier).setMode(selected);
                },
                child: Column(
                  children: [
                    for (final (mode, label, icon) in [
                      (ThemeMode.system, 'System', Icons.brightness_auto_rounded),
                      (ThemeMode.light, 'Light', Icons.light_mode_rounded),
                      (ThemeMode.dark, 'Dark', Icons.dark_mode_rounded),
                    ])
                      RadioListTile<ThemeMode>(
                        value: mode,
                        secondary: IconBadge(icon: icon),
                        title: Text(label),
                      ),
                  ],
                ),
              ),
              SwitchListTile(
                secondary: const IconBadge(icon: Icons.wallpaper_rounded),
                title: const Text('Dynamic colour'),
                subtitle: const Text('Match your device wallpaper theme, where supported'),
                value: dynamicColorEnabled,
                onChanged: (value) async {
                  await ref.read(localStoreProvider).setDynamicColorEnabled(value);
                  ref.invalidate(dynamicColorEnabledProvider);
                },
              ),
              const SectionHeader(title: 'Accessibility'),
              SwitchListTile(
                secondary: const IconBadge(icon: Icons.contrast_rounded),
                title: const Text('High contrast'),
                subtitle: const Text('Increases colour contrast throughout the app'),
                value: highContrast,
                onChanged: (value) async {
                  await ref.read(localStoreProvider).setHighContrast(value);
                  ref.invalidate(highContrastProvider);
                },
              ),
              ListTile(
                leading: const IconBadge(icon: Icons.text_fields_rounded),
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
              const SectionHeader(title: 'Privacy'),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const IconBadge(icon: Icons.privacy_tip_rounded),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Text(
                      'We only know you by an anonymous device token — no name, email or phone number '
                      "needed. Your location stays on this device and just helps us show what's nearby; "
                      "it's never sent anywhere. Your favourites, journeys and notifications are tied to "
                      "that anonymous token, so they're still here next time you open the app.",
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                  ),
                ],
              ),
              ListTile(
                leading: const IconBadge(icon: Icons.description_outlined),
                title: const Text('Privacy Policy'),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => context.push('/privacy-policy'),
              ),
              ListTile(
                leading: const IconBadge(icon: Icons.gavel_rounded),
                title: const Text('Terms of Use'),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => context.push('/terms-of-use'),
              ),
              const SectionHeader(title: 'Notifications'),
              SwitchListTile(
                secondary: const IconBadge(icon: Icons.notifications_active_rounded),
                title: const Text('Alerts and reminders'),
                subtitle: const Text(
                  'Destination, interchange, last-train, leave-home and service alerts',
                ),
                value: notificationsEnabled,
                onChanged: (value) async {
                  await ref.read(localStoreProvider).setNotificationsEnabled(value);
                  ref.invalidate(notificationsEnabledProvider);
                },
              ),
              ListTile(
                leading: const IconBadge(icon: Icons.inbox_rounded),
                title: const Text('View all notifications'),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => context.push('/notifications'),
              ),
              if (kDebugMode) ...[
                const SectionHeader(title: 'Backend'),
                ListTile(
                  leading: const IconBadge(icon: Icons.dns_rounded),
                  title: const Text('API server'),
                  subtitle: Text(apiBase),
                  trailing: const Icon(Icons.edit_rounded),
                  onTap: () => _editApiBase(context, ref),
                ),
              ],
              const SectionHeader(title: 'Offline data'),
              ListTile(
                leading: const IconBadge(icon: Icons.offline_pin_rounded),
                title: Text(bundle == null
                    ? 'Not downloaded'
                    : '${bundle.stations.length} stations · ${bundle.routes.length} lines cached'),
                subtitle: bundle == null ? null : Text('Dataset version ${bundle.version}'),
                trailing: bundleLoading
                    ? const Padding(
                        padding: EdgeInsets.all(13),
                        child: SizedBox(
                          width: 22,
                          height: 22,
                          child: CircularProgressIndicator(strokeWidth: 2.5),
                        ),
                      )
                    : IconPillButton(
                        icon: Icons.refresh_rounded,
                        tooltip: 'Refresh',
                        onPressed: () => ref.invalidate(offlineBundleProvider),
                      ),
              ),
              ListTile(
                leading: IconBadge(
                  icon: Icons.delete_outline_rounded,
                  color: AppColors.danger.withValues(alpha: 0.16),
                  foreground: AppColors.danger,
                ),
                title: const Text('Clear cached history and searches'),
                subtitle: const Text(
                  'Removes cached favourites, journey history and recent searches (station data is kept)',
                ),
                onTap: () => _confirmClearCache(context, ref),
              ),
              const SectionHeader(title: 'Support'),
              ListTile(
                leading: const IconBadge(icon: Icons.feedback_outlined),
                title: const Text('Send feedback'),
                subtitle: const Text('A bug, a suggestion, or just a thought — we read every one'),
                trailing: const Icon(Icons.chevron_right_rounded),
                onTap: () => showAppBottomSheet<void>(
                  context,
                  builder: (_) => const FeedbackSheet(),
                ),
              ),
              const SectionHeader(title: 'About'),
              ListTile(
                leading: IconBadge(icon: Icons.directions_subway_filled, gradient: AppColors.heroGradientFor()),
                title: const Text('MetroPulse'),
                subtitle: const Text('Version ${AppConfig.appVersion} · Metro Intelligence inside'),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _editApiBase(BuildContext context, WidgetRef ref) async {
    final store = ref.read(localStoreProvider);
    final controller = TextEditingController(text: store.apiBase);
    final result = await showAppBottomSheet<String>(
      context,
      builder: (sheetContext) => Padding(
        padding: const EdgeInsets.fromLTRB(AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('API server', style: Theme.of(sheetContext).textTheme.titleLarge),
            const SizedBox(height: AppSpacing.lg),
            TextField(
              controller: controller,
              autofocus: true,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(hintText: 'http://host:8000'),
            ),
            const SizedBox(height: AppSpacing.xl),
            Row(
              children: [
                Expanded(
                  child: GhostButton(
                    label: 'Cancel',
                    expand: true,
                    onPressed: () => Navigator.of(sheetContext).pop(),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: PrimaryButton(
                    label: 'Save',
                    expand: true,
                    onPressed: () => Navigator.of(sheetContext).pop(controller.text.trim()),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
    if (result != null && result.isNotEmpty) {
      await store.saveApiBase(result);
      ref.invalidate(apiBaseProvider);
      ref.invalidate(apiClientProvider);
    }
  }

  Future<void> _confirmClearCache(BuildContext context, WidgetRef ref) async {
    final confirmed = await showAppBottomSheet<bool>(
      context,
      builder: (sheetContext) => Padding(
        padding: const EdgeInsets.fromLTRB(AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Clear your cached data?', style: Theme.of(sheetContext).textTheme.titleLarge),
            const SizedBox(height: AppSpacing.sm),
            Text(
              "This clears your favourites, journey history and recent searches from this device. Don't "
              'worry — nothing is deleted from your account.',
              style: Theme.of(sheetContext).textTheme.bodyMedium,
            ),
            const SizedBox(height: AppSpacing.xl),
            Row(
              children: [
                Expanded(
                  child: GhostButton(
                    label: 'Cancel',
                    expand: true,
                    onPressed: () => Navigator.of(sheetContext).pop(false),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: PrimaryButton(
                    label: 'Clear',
                    expand: true,
                    onPressed: () => Navigator.of(sheetContext).pop(true),
                  ),
                ),
              ],
            ),
          ],
        ),
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
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Favourites, history and recent searches cleared')),
      );
    }
  }
}
