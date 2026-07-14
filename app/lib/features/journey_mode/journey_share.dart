import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/app_bottom_sheet.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import '../../core/widgets/icon_badge.dart';
import '../../data/location_service.dart';
import '../../providers/core_providers.dart';
import '../home/home_providers.dart' show locationServiceProvider;

/// The honest one-liner shown wherever the share is presented — this is the
/// user's OWN device GPS being broadcast to anyone holding the link, not the
/// train being tracked, and it says exactly that.
const _shareDisclosure =
    'Anyone with the link can see your live location until you arrive or stop sharing.';

typedef ShareJourneyFn = Future<Map<String, dynamic>?> Function(int journeyId);
typedef PostPositionFn = Future<void> Function(int journeyId, double lat, double lon);
typedef StopSharingFn = Future<void> Function(int journeyId);
typedef ResolvePositionFn = Future<LocationResult> Function();
typedef ExternalUrlLauncher = Future<bool> Function(Uri uri);

/// Share-my-live-journey: the in-journey control that creates a public share
/// link and then posts the device's own position every ~20s while active,
/// with a plainly-visible way to stop. Every backend call and the location
/// fix are injectable seams so the whole flow is testable without a network
/// or a real geolocator.
class JourneyShareButton extends ConsumerStatefulWidget {
  const JourneyShareButton({
    super.key,
    required this.journeyId,
    this.shareJourney,
    this.postPosition,
    this.stopSharing,
    this.resolvePosition,
    this.launchExternal,
    this.copyToClipboard,
    this.positionInterval = const Duration(seconds: 20),
  });

  final int journeyId;

  // Test seams — null means the real repository / services.
  final ShareJourneyFn? shareJourney;
  final PostPositionFn? postPosition;
  final StopSharingFn? stopSharing;
  final ResolvePositionFn? resolvePosition;
  final ExternalUrlLauncher? launchExternal;
  final Future<void> Function(String text)? copyToClipboard;

  /// How often the device position is posted while sharing. Kept short in
  /// tests so the loop can be exercised without a real 20s wait.
  final Duration positionInterval;

  @override
  ConsumerState<JourneyShareButton> createState() => _JourneyShareButtonState();
}

class _JourneyShareButtonState extends ConsumerState<JourneyShareButton> {
  bool _sharing = false;
  bool _starting = false;
  String? _shareUrl;
  Timer? _timer;

  ShareJourneyFn get _share =>
      widget.shareJourney ?? (id) => ref.read(journeyRepositoryProvider).shareJourney(id);
  PostPositionFn get _post =>
      widget.postPosition ?? (id, lat, lon) => ref.read(journeyRepositoryProvider).postSharePosition(id, lat, lon);
  StopSharingFn get _stop =>
      widget.stopSharing ?? (id) => ref.read(journeyRepositoryProvider).stopSharing(id);
  ResolvePositionFn get _resolve =>
      widget.resolvePosition ?? () => ref.read(locationServiceProvider).currentPosition();

  @override
  void dispose() {
    // Cancel the position loop, but never mark the share stopped here: the
    // share is meant to outlive a glance at another screen, and the backend
    // expires it on arrival anyway. Explicit Stop is the only thing that ends
    // it early.
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _startSharing() async {
    setState(() => _starting = true);
    final result = await _share(widget.journeyId);
    if (!mounted) return;
    final url = result?['share_url'] as String?;
    if (url == null) {
      setState(() => _starting = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Couldn't start sharing — check your connection and try again.")),
      );
      return;
    }
    setState(() {
      _sharing = true;
      _starting = false;
      _shareUrl = url;
    });
    // Post one fix immediately so the link isn't blank until the first tick.
    // That first push can itself stop sharing (location denied), so only arm
    // the interval and reveal the link if we're still sharing afterwards.
    await _pushPositionOnce();
    if (!mounted || !_sharing) return;
    _timer = Timer.periodic(widget.positionInterval, (_) => _pushPositionOnce());
    await _presentLink(url);
  }

  Future<void> _pushPositionOnce() async {
    final result = await _resolve();
    if (!mounted) return;
    switch (result) {
      case LocationFix(:final lat, :final lon):
        await _post(widget.journeyId, lat, lon);
      case LocationDenied():
        // Denial is the one case that ends sharing: without the user's own
        // GPS there is nothing honest to broadcast, so stop and say so.
        await _stopSharing(deniedLocation: true);
      case LocationUnavailable():
        // Transient (services off, no fix yet): keep the share alive so the
        // last-known position still shows, and try again next tick.
        break;
    }
  }

  Future<void> _stopSharing({bool deniedLocation = false}) async {
    _timer?.cancel();
    _timer = null;
    await _stop(widget.journeyId);
    if (!mounted) return;
    setState(() {
      _sharing = false;
      _shareUrl = null;
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          deniedLocation
              ? 'Location is off, so we stopped sharing your live trip.'
              : "You've stopped sharing this trip.",
        ),
      ),
    );
  }

  Future<void> _presentLink(String url) {
    return showAppBottomSheet<void>(
      context,
      builder: (sheetContext) => Padding(
        padding: const EdgeInsets.fromLTRB(AppSpacing.xl, AppSpacing.lg, AppSpacing.xl, AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Share your live trip', style: Theme.of(sheetContext).textTheme.titleLarge),
            const SizedBox(height: AppSpacing.sm),
            Text(_shareDisclosure, style: Theme.of(sheetContext).textTheme.bodyMedium),
            const SizedBox(height: AppSpacing.lg),
            GlassSurface(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Text(url, style: Theme.of(sheetContext).textTheme.bodyMedium),
            ),
            const SizedBox(height: AppSpacing.lg),
            Row(
              children: [
                Expanded(
                  child: GhostButton(
                    label: 'Open link',
                    icon: Icons.open_in_new_rounded,
                    expand: true,
                    onPressed: () => _openLink(url),
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: PrimaryButton(
                    label: 'Copy link',
                    icon: Icons.link_rounded,
                    expand: true,
                    onPressed: () => _copyLink(sheetContext, url),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _copyLink(BuildContext sheetContext, String url) async {
    final copy = widget.copyToClipboard ?? (text) => Clipboard.setData(ClipboardData(text: text));
    await copy(url);
    if (sheetContext.mounted) {
      ScaffoldMessenger.of(sheetContext).showSnackBar(
        const SnackBar(content: Text('Live trip link copied')),
      );
    }
  }

  Future<void> _openLink(String url) async {
    final launch = widget.launchExternal ?? (uri) => launchUrl(uri, mode: LaunchMode.externalApplication);
    final ok = await launch(Uri.parse(url));
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Couldn't open that link on this device.")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (!_sharing) {
      return GhostButton(
        label: _starting ? 'Starting…' : 'Share my trip',
        icon: Icons.ios_share_rounded,
        expand: true,
        onPressed: _starting ? null : _startSharing,
      );
    }
    return GlassSurface(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              IconBadge(
                icon: Icons.wifi_tethering_rounded,
                color: AppColors.live.withValues(alpha: 0.16),
                foreground: AppColors.live,
              ),
              const SizedBox(width: AppSpacing.md),
              Expanded(
                child: Text("You're sharing this trip", style: theme.textTheme.titleMedium),
              ),
              TextButton(
                onPressed: () => _stopSharing(),
                child: const Text('Stop'),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(
            _shareDisclosure,
            style: theme.textTheme.labelMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          ),
          if (_shareUrl != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: () => _presentLink(_shareUrl!),
                icon: const Icon(Icons.link_rounded, size: 18),
                label: const Text('Show link'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
