import 'dart:async';

import 'package:flutter/material.dart';

/// Fades + slides [child] in, optionally after [delay] — used to stagger
/// list/section entrances so a screen feels like it's arriving, not just
/// appearing.
class DelayedReveal extends StatefulWidget {
  const DelayedReveal({
    super.key,
    required this.child,
    this.delay = Duration.zero,
    this.duration = const Duration(milliseconds: 550),
    this.curve = Curves.easeOutCubic,
    this.slideFrom = const Offset(0, 0.08),
  });

  final Widget child;
  final Duration delay;
  final Duration duration;
  final Curve curve;
  final Offset slideFrom;

  @override
  State<DelayedReveal> createState() => _DelayedRevealState();
}

class _DelayedRevealState extends State<DelayedReveal> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, duration: widget.duration);
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer(widget.delay, () {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final curved = CurvedAnimation(parent: _controller, curve: widget.curve);
    return AnimatedBuilder(
      animation: curved,
      builder: (context, child) {
        return Opacity(
          opacity: curved.value.clamp(0.0, 1.0),
          child: Transform.translate(
            offset: widget.slideFrom * (1 - curved.value),
            child: child,
          ),
        );
      },
      child: widget.child,
    );
  }
}

/// A coloured bar that "draws" itself in from the left — the animated
/// route-line effect on the Journey Planner's route visualisation.
class DrawnBar extends StatefulWidget {
  const DrawnBar({
    super.key,
    required this.color,
    this.height = 6,
    this.delay = Duration.zero,
    this.duration = const Duration(milliseconds: 650),
  });

  final Color color;
  final double height;
  final Duration delay;
  final Duration duration;

  @override
  State<DrawnBar> createState() => _DrawnBarState();
}

class _DrawnBarState extends State<DrawnBar> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this, duration: widget.duration);
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer(widget.delay, () {
      if (mounted) _controller.forward();
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final t = Curves.easeOutCubic.transform(_controller.value).clamp(0.0001, 1.0);
        return Align(
          alignment: Alignment.centerLeft,
          child: FractionallySizedBox(
            widthFactor: t,
            child: Container(
              height: widget.height,
              decoration:
                  BoxDecoration(color: widget.color, borderRadius: BorderRadius.circular(widget.height / 2)),
            ),
          ),
        );
      },
    );
  }
}
