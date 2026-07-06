import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/design/app_spacing.dart';
import '../../core/widgets/gradient_button.dart';
import '../../providers/core_providers.dart';

/// The "Send feedback" bottom sheet -- an optional category, a message, and
/// a submit button that honestly reports whether it actually went through.
class FeedbackSheet extends ConsumerStatefulWidget {
  const FeedbackSheet({super.key});

  @override
  ConsumerState<FeedbackSheet> createState() => _FeedbackSheetState();
}

class _FeedbackSheetState extends ConsumerState<FeedbackSheet> {
  final _controller = TextEditingController();
  String? _category;
  bool _submitting = false;

  static const _categories = [
    (value: 'bug', label: 'Bug'),
    (value: 'suggestion', label: 'Suggestion'),
    (value: 'praise', label: 'Praise'),
    (value: 'other', label: 'Other'),
  ];

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final message = _controller.text.trim();
    if (message.isEmpty || _submitting) return;
    setState(() => _submitting = true);
    final messenger = ScaffoldMessenger.of(context);
    final navigator = Navigator.of(context);
    try {
      await ref.read(feedbackRepositoryProvider).submit(message: message, category: _category);
      if (!mounted) return;
      navigator.pop();
      messenger.showSnackBar(const SnackBar(content: Text('Thanks — feedback sent!')));
    } on Exception {
      if (!mounted) return;
      setState(() => _submitting = false);
      messenger.showSnackBar(
        const SnackBar(content: Text("Couldn't send that — check your connection and try again.")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.xl,
        AppSpacing.lg,
        AppSpacing.xl,
        MediaQuery.of(context).viewInsets.bottom + AppSpacing.xxl,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Send feedback', style: theme.textTheme.titleLarge),
          const SizedBox(height: AppSpacing.sm),
          Text(
            "Tell us what's working, what's not, or what you'd like to see.",
            style: theme.textTheme.bodyMedium,
          ),
          const SizedBox(height: AppSpacing.lg),
          Wrap(
            spacing: AppSpacing.sm,
            children: [
              for (final option in _categories)
                ChoiceChip(
                  label: Text(option.label),
                  selected: _category == option.value,
                  onSelected: (selected) => setState(() => _category = selected ? option.value : null),
                ),
            ],
          ),
          const SizedBox(height: AppSpacing.lg),
          TextField(
            controller: _controller,
            autofocus: true,
            minLines: 4,
            maxLines: 8,
            maxLength: 4000,
            decoration: const InputDecoration(hintText: 'What would you like to tell us?'),
          ),
          const SizedBox(height: AppSpacing.md),
          PrimaryButton(
            label: _submitting ? 'Sending…' : 'Send',
            expand: true,
            onPressed: _submitting ? null : _submit,
          ),
        ],
      ),
    );
  }
}
