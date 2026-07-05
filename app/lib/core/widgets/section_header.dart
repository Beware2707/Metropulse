import 'package:flutter/material.dart';

import '../design/app_spacing.dart';

/// A bold, typography-forward section title — replaces small Material
/// `titleMedium` row headers throughout the app.
class SectionHeader extends StatelessWidget {
  const SectionHeader({super.key, required this.title, this.trailing, this.padding});

  final String title;
  final Widget? trailing;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: padding ?? const EdgeInsets.only(bottom: AppSpacing.md, top: AppSpacing.xxl),
      child: Row(
        children: [
          Expanded(child: Text(title, style: theme.textTheme.headlineSmall)),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}
