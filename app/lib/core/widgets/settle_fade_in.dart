import 'package:flutter/material.dart';

import '../design/app_motion.dart';

/// Fades [child] in only after its first layout pass has settled, rather
/// than showing it immediately at whatever position the very first frame
/// computes. Flutter web's first frame can briefly report a viewport size
/// that isn't final (before browser chrome/fonts finish settling), which
/// would otherwise flash a fixed-position overlay — a floating button, say
/// — somewhere it doesn't actually belong once layout stabilizes.
class SettleFadeIn extends StatefulWidget {
  const SettleFadeIn({super.key, required this.child});

  final Widget child;

  @override
  State<SettleFadeIn> createState() => _SettleFadeInState();
}

class _SettleFadeInState extends State<SettleFadeIn> {
  bool _visible = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) setState(() => _visible = true);
    });
  }

  @override
  Widget build(BuildContext context) {
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    return AnimatedOpacity(
      opacity: _visible ? 1.0 : 0.0,
      duration: reduceMotion ? Duration.zero : AppMotion.fast,
      child: widget.child,
    );
  }
}
