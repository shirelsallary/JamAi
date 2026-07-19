import 'package:flutter/material.dart';
import '../theme.dart';

/// Full-width pill button with the Dusk gradient fill and soft glow, used
/// for every primary call-to-action. Owns its own loading-spinner swap so
/// call sites stop reimplementing the spinner-in-button pattern that was
/// previously copy-pasted across five screens.
///
/// ThemeData/ElevatedButtonThemeData can't express a gradient fill, which is
/// why this is a standalone widget rather than an ElevatedButton style.
class PrimaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool isLoading;
  final IconData? icon;

  const PrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.isLoading = false,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final disabled = onPressed == null;
    final contentColor = disabled ? kTextSecondary : Colors.white;

    return SizedBox(
      width: double.infinity,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(kRadiusPill),
          gradient: disabled ? null : const LinearGradient(colors: kPrimaryGradient),
          color: disabled ? kSurface : null,
          boxShadow: disabled
              ? null
              : [
                  BoxShadow(
                    color: kPrimaryGradientStart.withAlpha(kAlphaMedium),
                    blurRadius: 20,
                    offset: const Offset(0, 8),
                  ),
                ],
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            borderRadius: BorderRadius.circular(kRadiusPill),
            onTap: disabled || isLoading ? null : onPressed,
            child: Container(
              height: 52,
              alignment: Alignment.center,
              padding: const EdgeInsets.symmetric(horizontal: kSpaceLg),
              child: isLoading
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (icon != null) ...[
                          Icon(icon, color: contentColor, size: 20),
                          const SizedBox(width: kSpaceSm),
                        ],
                        Text(
                          label,
                          style: TextStyle(
                            color: contentColor,
                            fontWeight: FontWeight.w700,
                            fontSize: 16,
                          ),
                        ),
                      ],
                    ),
            ),
          ),
        ),
      ),
    );
  }
}
