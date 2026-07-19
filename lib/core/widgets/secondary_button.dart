import 'package:flutter/material.dart';
import '../theme.dart';

/// Full-width pill button with a translucent fill and subtle border — the
/// secondary-action counterpart to [PrimaryButton] (e.g. "Share link",
/// "End & export queue" in the mockup). Same loading-spinner support as
/// PrimaryButton so both share one mental model.
class SecondaryButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final bool isLoading;
  final IconData? icon;

  const SecondaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.isLoading = false,
    this.icon,
  });

  @override
  Widget build(BuildContext context) {
    final disabled = onPressed == null;
    final contentColor = disabled ? kTextSecondary : kTextPrimary;

    return SizedBox(
      width: double.infinity,
      child: DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(kRadiusPill),
          color: kCardSurface,
          border: Border.all(
            color: kTextSecondary.withAlpha(disabled ? kAlphaSubtle : kAlphaMedium),
          ),
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
                  ? SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: contentColor),
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
