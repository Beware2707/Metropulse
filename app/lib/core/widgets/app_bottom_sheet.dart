import 'dart:ui';

import 'package:flutter/material.dart';

import '../design/app_radius.dart';

/// The one bottom-sheet treatment used everywhere: blurred glass, 32dp
/// rounded top corners, a drag handle — replaces ad-hoc
/// `showModalBottomSheet` styling scattered per call site.
Future<T?> showAppBottomSheet<T>(
  BuildContext context, {
  required WidgetBuilder builder,
  bool isScrollControlled = true,
}) {
  final scheme = Theme.of(context).colorScheme;
  const radius = BorderRadius.vertical(top: Radius.circular(AppRadius.xxl));
  return showModalBottomSheet<T>(
    context: context,
    isScrollControlled: isScrollControlled,
    backgroundColor: Colors.transparent,
    builder: (sheetContext) => ClipRRect(
      borderRadius: radius,
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30),
        child: Container(
          decoration: BoxDecoration(
            color: scheme.surfaceContainerHighest.withValues(alpha: 0.94),
            borderRadius: radius,
            border: Border(top: BorderSide(color: scheme.outlineVariant)),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const SizedBox(height: 12),
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(color: scheme.outlineVariant, borderRadius: BorderRadius.circular(2)),
              ),
              const SizedBox(height: 8),
              builder(sheetContext),
            ],
          ),
        ),
      ),
    ),
  );
}
