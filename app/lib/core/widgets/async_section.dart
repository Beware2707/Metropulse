import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../design/app_spacing.dart';
import 'empty_state.dart';
import 'section_header.dart';
import 'shimmer_skeleton.dart';

/// A titled section wrapping an [AsyncValue] with consistent
/// loading-shimmer / error / empty / data states, in the new visual language.
class AsyncSection<T> extends ConsumerWidget {
  const AsyncSection({
    super.key,
    required this.title,
    required this.value,
    required this.builder,
    required this.emptyMessage,
    required this.isEmpty,
    this.onRetry,
    this.skeletonHeight = 84,
    this.trailing,
    this.emptyIcon = Icons.inbox_rounded,
  });

  final String title;
  final AsyncValue<T> value;
  final Widget Function(BuildContext context, T data) builder;
  final String emptyMessage;
  final bool Function(T data) isEmpty;
  final VoidCallback? onRetry;
  final double skeletonHeight;
  final Widget? trailing;
  final IconData emptyIcon;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionHeader(
          title: title,
          trailing: trailing,
          padding: const EdgeInsets.only(bottom: AppSpacing.md, top: AppSpacing.xxxl),
        ),
        value.when(
          loading: () => ShimmerBlock(height: skeletonHeight),
          error: (error, _) => EmptyState(
            icon: Icons.cloud_off_rounded,
            message: "Hmm, that didn't load.",
            actionLabel: onRetry == null ? null : 'Try again',
            onAction: onRetry,
          ),
          data: (data) =>
              isEmpty(data) ? EmptyState(icon: emptyIcon, message: emptyMessage) : builder(context, data),
        ),
      ],
    );
  }
}
