import 'package:flutter/material.dart';

import '../design/app_motion.dart';

/// The flagship animated journey-progress track: a capsule rail that fills
/// with a gradient and carries a glowing "you are here" dot which glides
/// smoothly to its new position whenever `fraction` changes — whether that
/// change came from a live vehicle fix or a GTFS-timetable estimate.
class JourneyProgressTrack extends StatelessWidget {
  const JourneyProgressTrack({super.key, required this.fraction, this.height = 12, this.color});

  final double? fraction;
  final double height;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    final tint = color ?? scheme.primary;
    final value = (fraction ?? 0).clamp(0.0, 1.0);
    return SizedBox(
      height: height + 24,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final trackWidth = constraints.maxWidth;
          return Stack(
            alignment: Alignment.centerLeft,
            children: [
              Container(
                height: height,
                width: trackWidth,
                decoration: BoxDecoration(
                  color: scheme.surfaceContainerHighest,
                  borderRadius: BorderRadius.circular(height / 2),
                ),
              ),
              if (reduceMotion)
                Builder(
                  builder: (context) {
                    final fillWidth = (trackWidth * value).clamp(height, trackWidth);
                    return Stack(
                      clipBehavior: Clip.none,
                      alignment: Alignment.centerLeft,
                      children: [
                        Container(
                          height: height,
                          width: fillWidth,
                          decoration: BoxDecoration(
                            gradient: LinearGradient(colors: [tint, tint.withValues(alpha: 0.65)]),
                            borderRadius: BorderRadius.circular(height / 2),
                          ),
                        ),
                        Positioned(
                          left: (fillWidth - 12).clamp(-12.0, trackWidth - 12),
                          child: _GlowDot(color: tint),
                        ),
                      ],
                    );
                  },
                )
              else
                TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: value),
                  duration: AppMotion.glide,
                  curve: AppMotion.standard,
                  builder: (context, animated, _) {
                    final fillWidth = (trackWidth * animated).clamp(height, trackWidth);
                    return Stack(
                      clipBehavior: Clip.none,
                      alignment: Alignment.centerLeft,
                      children: [
                        Container(
                          height: height,
                          width: fillWidth,
                          decoration: BoxDecoration(
                            gradient: LinearGradient(colors: [tint, tint.withValues(alpha: 0.65)]),
                            borderRadius: BorderRadius.circular(height / 2),
                          ),
                        ),
                        Positioned(
                          left: (fillWidth - 12).clamp(-12.0, trackWidth - 12),
                          child: _GlowDot(color: tint),
                        ),
                      ],
                    );
                  },
                ),
            ],
          );
        },
      ),
    );
  }
}

class _GlowDot extends StatefulWidget {
  const _GlowDot({required this.color});

  final Color color;

  @override
  State<_GlowDot> createState() => _GlowDotState();
}

class _GlowDotState extends State<_GlowDot> with SingleTickerProviderStateMixin {
  late final AnimationController _controller =
      AnimationController(vsync: this, duration: AppMotion.pulse)..repeat(reverse: true);

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    if (reduceMotion) {
      return Container(
        width: 24,
        height: 24,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Colors.white,
          border: Border.all(color: widget.color, width: 3),
          boxShadow: [BoxShadow(color: widget.color.withValues(alpha: 0.6), blurRadius: 8)],
        ),
      );
    }
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final glow = 6 + _controller.value * 8;
        return Container(
          width: 24,
          height: 24,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: Colors.white,
            border: Border.all(color: widget.color, width: 3),
            boxShadow: [
              BoxShadow(color: widget.color.withValues(alpha: 0.75), blurRadius: glow, spreadRadius: 1),
            ],
          ),
        );
      },
    );
  }
}
