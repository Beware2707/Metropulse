import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_radius.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/glass_surface.dart';
import '../../core/widgets/gradient_button.dart';
import 'legal_content.dart';

/// Renders a Privacy Policy / Terms of Use document from its structured
/// [LegalBlock] content -- no markdown dependency, just plain widgets.
class LegalDocScreen extends StatelessWidget {
  const LegalDocScreen({super.key, required this.title, required this.blocks});

  final String title;
  final List<LegalBlock> blocks;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: AmbientBackground(
        intensity: 0.5,
        child: SafeArea(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(AppSpacing.lg, AppSpacing.lg, AppSpacing.lg, AppSpacing.xxl),
            children: [
              Row(
                children: [
                  IconPillButton(icon: Icons.arrow_back_rounded, onPressed: () => context.pop()),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(child: Text(title, style: theme.textTheme.displaySmall)),
                ],
              ),
              const SizedBox(height: AppSpacing.xs),
              Padding(
                padding: const EdgeInsets.only(left: 52),
                child: Text('Last updated $legalLastUpdated', style: theme.textTheme.labelMedium),
              ),
              const SizedBox(height: AppSpacing.xl),
              for (final block in blocks) _blockWidget(context, block),
            ],
          ),
        ),
      ),
    );
  }

  Widget _blockWidget(BuildContext context, LegalBlock block) {
    final theme = Theme.of(context);
    return switch (block) {
      LegalNotice(:final text) => Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.lg),
          child: GlassSurface(
            borderRadius: AppRadius.lgR,
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.info_outline_rounded, size: 20, color: AppColors.warning),
                const SizedBox(width: AppSpacing.md),
                Expanded(
                  child: Text(text, style: theme.textTheme.bodyMedium?.copyWith(color: AppColors.warning)),
                ),
              ],
            ),
          ),
        ),
      LegalHeading(:final text) => Padding(
          padding: const EdgeInsets.only(top: AppSpacing.lg, bottom: AppSpacing.sm),
          child: Text(text, style: theme.textTheme.titleLarge),
        ),
      LegalParagraph(:final text) => Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.md),
          child: Text(text, style: theme.textTheme.bodyMedium),
        ),
      LegalItem(:final title, :final body) => Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.md),
          child: RichText(
            text: TextSpan(
              style: theme.textTheme.bodyMedium,
              children: [
                TextSpan(text: '$title ', style: const TextStyle(fontWeight: FontWeight.w700)),
                TextSpan(text: body),
              ],
            ),
          ),
        ),
      LegalBullets(:final items) => Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final item in items)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('•  ', style: theme.textTheme.bodyMedium),
                      Expanded(child: Text(item, style: theme.textTheme.bodyMedium)),
                    ],
                  ),
                ),
            ],
          ),
        ),
    };
  }
}
