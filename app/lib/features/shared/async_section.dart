import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

/// A pulsing placeholder block shown while a section loads.
///
/// Hand-rolled (no shimmer dependency): a single looping opacity tween is
/// cheap, respects the theme in both modes, and honours reduced-motion
/// accessibility settings by freezing at mid-opacity.
class SkeletonBlock extends StatefulWidget {
  const SkeletonBlock({super.key, this.height = 72, this.width, this.radius = 16});

  final double height;
  final double? width;
  final double radius;

  @override
  State<SkeletonBlock> createState() => _SkeletonBlockState();
}

class _SkeletonBlockState extends State<SkeletonBlock>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );

  @override
  void initState() {
    super.initState();
    _controller.repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.surfaceContainerHighest;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final block = Container(
      height: widget.height,
      width: widget.width,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(widget.radius),
      ),
    );
    if (reduceMotion) return Opacity(opacity: 0.6, child: block);
    return FadeTransition(
      opacity: Tween(begin: 0.35, end: 0.85).animate(_controller),
      child: block,
    );
  }
}

/// A titled home-screen section wrapping an [AsyncValue] with consistent
/// loading-skeleton / error / empty / data states.
class AsyncSection<T> extends ConsumerWidget {
  const AsyncSection({
    super.key,
    required this.title,
    required this.value,
    required this.builder,
    required this.emptyMessage,
    required this.isEmpty,
    this.onRetry,
    this.skeletonHeight = 72,
    this.trailing,
  });

  final String title;
  final AsyncValue<T> value;
  final Widget Function(BuildContext context, T data) builder;
  final String emptyMessage;
  final bool Function(T data) isEmpty;
  final VoidCallback? onRetry;
  final double skeletonHeight;
  final Widget? trailing;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: 8, top: 16),
          child: Row(
            children: [
              Expanded(
                child: Text(title,
                    style: theme.textTheme.titleMedium
                        ?.copyWith(fontWeight: FontWeight.w600)),
              ),
              if (trailing != null) trailing!,
            ],
          ),
        ),
        value.when(
          loading: () => SkeletonBlock(height: skeletonHeight),
          error: (error, _) => _ErrorCard(onRetry: onRetry),
          data: (data) => isEmpty(data)
              ? _EmptyCard(message: emptyMessage)
              : builder(context, data),
        ),
      ],
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({this.onRetry});

  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: ListTile(
        leading: Icon(Icons.cloud_off, color: scheme.error),
        title: const Text("Couldn't load this section."),
        trailing: onRetry == null
            ? null
            : TextButton(onPressed: onRetry, child: const Text('Retry')),
      ),
    );
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Text(message, style: Theme.of(context).textTheme.bodyMedium),
      ),
    );
  }
}
