import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/design/app_colors.dart';
import '../../core/design/app_spacing.dart';
import '../../core/widgets/ambient_background.dart';
import '../../core/widgets/gradient_button.dart';
import '../../providers/core_providers.dart';

class _OnboardingSlide {
  const _OnboardingSlide({required this.icon, required this.title, required this.body});
  final IconData icon;
  final String title;
  final String body;
}

const _slides = [
  _OnboardingSlide(
    icon: Icons.directions_subway_filled_rounded,
    title: 'Your Delhi Metro companion',
    body: 'Plan journeys, track trains, and get where you\'re going with one app built around '
        'how you actually ride.',
  ),
  _OnboardingSlide(
    icon: Icons.map_rounded,
    title: 'Watch trains move, honestly',
    body: 'The live map always tells you the truth about what you\'re seeing — real GPS when '
        'available, clearly labelled schedule estimates when it isn\'t.',
  ),
  _OnboardingSlide(
    icon: Icons.chair_alt_rounded,
    title: 'The right coach, the right exit',
    body: 'Get a coach recommendation based on real crowding data and the exit closest to '
        'where you\'re headed — every time.',
  ),
  _OnboardingSlide(
    icon: Icons.notifications_active_rounded,
    title: "We'll tell you when to leave",
    body: 'Save Home and Work, and MetroPulse learns your commute — nudging you at the right '
        'moment instead of making you check.',
  ),
];

/// First-launch onboarding, shown once before the splash screen's boot flow
/// reaches the home screen -- see [LocalStore.hasCompletedOnboarding].
class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final _controller = PageController();
  int _page = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _finish() async {
    await ref.read(localStoreProvider).markOnboardingCompleted();
    if (mounted) context.go('/');
  }

  void _next() {
    if (_page == _slides.length - 1) {
      _finish();
      return;
    }
    _controller.nextPage(duration: const Duration(milliseconds: 300), curve: Curves.easeOut);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isLast = _page == _slides.length - 1;
    return Scaffold(
      body: AmbientBackground(
        intensity: 1.0,
        child: SafeArea(
          child: Column(
            children: [
              Align(
                alignment: Alignment.topRight,
                child: Padding(
                  padding: const EdgeInsets.all(AppSpacing.lg),
                  child: GhostButton(label: 'Skip', onPressed: _finish),
                ),
              ),
              Expanded(
                child: PageView.builder(
                  controller: _controller,
                  itemCount: _slides.length,
                  onPageChanged: (index) => setState(() => _page = index),
                  itemBuilder: (context, index) {
                    final slide = _slides[index];
                    return Padding(
                      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xxl),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Container(
                            width: 96,
                            height: 96,
                            decoration: BoxDecoration(
                              gradient: AppColors.heroGradientFor(),
                              borderRadius: BorderRadius.circular(28),
                            ),
                            child: Icon(slide.icon, color: Colors.white, size: 44),
                          ),
                          const SizedBox(height: AppSpacing.xxl),
                          Text(
                            slide.title,
                            textAlign: TextAlign.center,
                            style: theme.textTheme.headlineMedium,
                          ),
                          const SizedBox(height: AppSpacing.md),
                          Text(
                            slide.body,
                            textAlign: TextAlign.center,
                            style: theme.textTheme.bodyLarge,
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  for (var i = 0; i < _slides.length; i++)
                    AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      margin: const EdgeInsets.symmetric(horizontal: 4),
                      width: i == _page ? 24 : 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: i == _page
                            ? AppColors.brandBlue
                            : theme.colorScheme.onSurface.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                ],
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(AppSpacing.xxl, AppSpacing.xl, AppSpacing.xxl, AppSpacing.xxl),
                child: PrimaryButton(
                  label: isLast ? 'Get started' : 'Next',
                  expand: true,
                  onPressed: _next,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
