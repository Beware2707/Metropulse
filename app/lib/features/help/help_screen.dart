import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../core/widgets/section_header.dart';

/// DMRC's published 24/7 rider helpline. Verified DMRC contact — do not
/// change without re-verifying against DMRC's own published information.
const String dmrcHelplineNumber = '155370';

/// DMRC/CISF security helpline. Verified DMRC contact.
const String dmrcSecurityNumber = '155655';

/// How the screen places a phone call. Injectable so tests can observe the
/// hand-off without a host platform; defaults to the real url_launcher.
/// Mirrors the seam in [TicketsScreen].
typedef ExternalUrlLauncher = Future<bool> Function(Uri uri);

/// Help & lost property: DMRC's real, published rider contacts and honest
/// guidance for recovering a lost item. MetroPulse only surfaces DMRC's own
/// numbers — it never runs a lost-property desk itself, and it invents no
/// contact details. The two helpline rows dial DMRC directly via `tel:`.
class HelpScreen extends StatelessWidget {
  const HelpScreen({super.key, this.launchExternal});

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
            padding: const EdgeInsets.fromLTRB(
                AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, 48),
            children: [
              Row(
                children: [
                  IconPillButton(
                      icon: Icons.arrow_back_rounded,
                      onPressed: () => context.pop()),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: Text('Help & lost property',
                        style: theme.textTheme.displaySmall),
                  ),
                ],
              ),
              const SizedBox(height: AppSpacing.lg),
              Text(
                'DMRC published contacts. These are the Delhi Metro’s own '
                'official helplines — MetroPulse just puts them a tap away.',
                style: theme.textTheme.bodyMedium,
              ),
              const SectionHeader(title: 'Call for help'),
              ListTile(
                leading: const IconBadge(icon: Icons.support_agent_rounded),
                title: const Text('DMRC helpline (24/7)'),
                subtitle: const Text(
                  'General help, enquiries and lost property · $dmrcHelplineNumber',
                ),
                trailing: const Icon(Icons.call_rounded, size: 20),
                onTap: () => _call(context, dmrcHelplineNumber),
              ),
              ListTile(
                leading: const IconBadge(icon: Icons.security_rounded),
                title: const Text('Security / CISF helpline'),
                subtitle: const Text(
                  'For safety and security concerns in the Metro · $dmrcSecurityNumber',
                ),
                trailing: const Icon(Icons.call_rounded, size: 20),
                onTap: () => _call(context, dmrcSecurityNumber),
              ),
              const SectionHeader(title: 'Lost something?'),
              GlassSurface(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const IconBadge(icon: Icons.inventory_2_rounded),
                    const SizedBox(width: AppSpacing.md),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Recovering a lost item',
                              style: theme.textTheme.titleMedium),
                          const SizedBox(height: AppSpacing.xs),
                          Text(
                            'Call $dmrcHelplineNumber or visit any station as soon as you can. '
                            'Items are held about 3 months; there’s no fee to claim.',
                            style: theme.textTheme.bodyMedium,
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: AppSpacing.sm),
              PrimaryButton(
                label: 'Call the DMRC helpline',
                icon: Icons.call_rounded,
                expand: true,
                onPressed: () => _call(context, dmrcHelplineNumber),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// Places a call via the device dialler (`tel:`), with an honest SnackBar
  /// when the device has no way to dial (e.g. a tablet without telephony).
  Future<void> _call(BuildContext context, String number) async {
    final launch = launchExternal ??
        (uri) => launchUrl(uri, mode: LaunchMode.externalApplication);
    final ok = await launch(Uri(scheme: 'tel', path: number));
    if (!ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("Couldn't open the dialler — you can call $number directly."),
        ),
      );
    }
  }
}
