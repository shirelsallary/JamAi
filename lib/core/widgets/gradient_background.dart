import 'package:flutter/material.dart';
import '../theme.dart';

/// The Dusk background treatment: a near-black purple base with two soft
/// radial glows — deep violet/indigo in the upper portion, warm
/// coral-orange in the lower portion — applied consistently behind every
/// screen's content, per the mockup spec. Wrap a screen's body with this
/// (e.g. `body: GradientBackground(child: ...)`) rather than relying on
/// `scaffoldBackgroundColor`, which can only express a flat fill.
class GradientBackground extends StatelessWidget {
  final Widget child;

  const GradientBackground({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        const ColoredBox(color: kBackground),
        Align(
          alignment: const Alignment(0, -1.1),
          child: _Glow(color: kGlowViolet, size: 520),
        ),
        Align(
          alignment: const Alignment(0, 1.2),
          child: _Glow(color: kGlowCoral, size: 480),
        ),
        child,
      ],
    );
  }
}

class _Glow extends StatelessWidget {
  final Color color;
  final double size;

  const _Glow({required this.color, required this.size});

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            colors: [color.withAlpha(140), color.withAlpha(0)],
          ),
        ),
      ),
    );
  }
}
