import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/config.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/section_header.dart';

/// How the screen opens a channel URL. Injectable so tests can observe the
/// hand-off without a host platform; defaults to the real url_launcher.
typedef ExternalUrlLauncher = Future<bool> Function(Uri uri);

/// Tickets & recharge: a fare-aware hand-off to DMRC's official purchase
/// channels. MetroPulse deliberately never handles money — no payment SDKs,
/// no wallet, no order state. Every row here opens one of DMRC's own rails
/// (WhatsApp bot, web portal, Momentum 2.0, smart-card recharge site, or
/// Autope, the one DMRC-authorised auto top-up issuer) and the user pays
/// DMRC directly there.
class TicketsScreen extends StatelessWidget {
  const TicketsScreen({super.key, this.launchExternal});

  /// Test seam — see [ExternalUrlLauncher]. Null means the real launcher.
  final ExternalUrlLauncher? launchExternal;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 48),
            children: [
              Row(
                children: [
                  IconPillButton(icon: Icons.arrow_back_rounded, onPressed: () => context.pop()),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Text('Tickets & recharge', style: theme.textTheme.displaySmall),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              Text(
                'Buy directly from DMRC — payments happen on their official, secure channels. '
                'MetroPulse never handles your money.',
                style: theme.textTheme.bodyMedium,
              ),
              const SectionHeader(title: 'Buy QR tickets'),
              ListTile(
                leading: const IconBadge(icon: Icons.chat_rounded),
                title: const Text('WhatsApp ticketing'),
                subtitle: const Text(
                  'Chat with DMRC on WhatsApp — pay by UPI or card. '
                  'Tickets bookable roughly 6 am to 9 pm.',
                ),
                trailing: const Icon(Icons.open_in_new_rounded, size: 18),
                onTap: () => _openChannel(context, AppConfig.dmrcWhatsAppTicketsUrl),
              ),
              ListTile(
                leading: const IconBadge(icon: Icons.qr_code_2_rounded),
                title: const Text('DMRC web ticket portal'),
                subtitle: const Text("Buy QR tickets in your browser, on DMRC's official site"),
                trailing: const Icon(Icons.open_in_new_rounded, size: 18),
                onTap: () => _openChannel(context, AppConfig.dmrcQrPortalUrl),
              ),
              ListTile(
                leading: const IconBadge(icon: Icons.smartphone_rounded),
                title: const Text('DMRC Momentum 2.0 app'),
                subtitle: const Text(
                  "DMRC's official app for QR tickets, wallet and card recharge — on the Play Store",
                ),
                trailing: const Icon(Icons.open_in_new_rounded, size: 18),
                onTap: () => _openChannel(context, AppConfig.dmrcMomentumStoreUrl),
              ),
              const SectionHeader(title: 'Smart card recharge'),
              ListTile(
                leading: const IconBadge(icon: Icons.credit_card_rounded),
                title: const Text('Official online recharge'),
                subtitle: const Text(
                  'Top up online, then tap your card on any station AVM to load the balance',
                ),
                trailing: const Icon(Icons.open_in_new_rounded, size: 18),
                onTap: () => _openChannel(context, AppConfig.dmrcCardRechargeUrl),
              ),
              ListTile(
                leading: const IconBadge(icon: Icons.autorenew_rounded),
                title: const Text('Autope auto top-up'),
                subtitle: const Text(
                  'Auto-recharges at the gate when the balance runs low — '
                  'the only DMRC-authorised auto top-up',
                ),
                trailing: const Icon(Icons.open_in_new_rounded, size: 18),
                onTap: () => _openChannel(context, AppConfig.autopeUrl),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// The one launch path every row shares.
  ///
  /// Tries a native app first (WhatsApp, the Play Store), then falls back to
  /// the platform default so a plain web link still opens in a browser or a
  /// custom tab. Both halves matter: `externalApplication` alone was the
  /// shipped bug — on Android 11+ it resolves only apps the manifest can see,
  /// so `wa.me` opened via WhatsApp's verified App Links while DMRC's portal,
  /// the recharge site and Autope all silently did nothing.
  ///
  /// The failure message names the real cause. The old copy blamed the
  /// connection, which sent people to check their wifi over a problem that
  /// had nothing to do with it.
  Future<void> _openChannel(BuildContext context, String url) async {
    final uri = Uri.parse(url);
    final launch = launchExternal ??
        (u) async {
          try {
            if (await launchUrl(u, mode: LaunchMode.externalApplication)) {
              return true;
            }
          } on PlatformException {
            // No app claims this link; the platform default can still take it.
          }
          try {
            return await launchUrl(u, mode: LaunchMode.platformDefault);
          } on PlatformException {
            return false;
          }
        };
    final ok = await launch(uri);
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text("Couldn't open that link on this device."),
          action: SnackBarAction(
            label: 'Copy link',
            onPressed: () => Clipboard.setData(ClipboardData(text: url)),
          ),
        ),
      );
    }
  }
}
