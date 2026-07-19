import 'package:flutter/material.dart';
import '../theme.dart';

/// Which tone an [AppBanner] communicates. Each maps to a theme.dart color
/// token — no colors are invented locally, so a banner's tone always tracks
/// the app's palette if it changes.
enum AppBannerVariant { error, info, success, warning }

/// A tinted inline banner for surfacing a status message, with an optional
/// action button (e.g. "Retry") that can show its own loading state.
///
/// Generalized from what was originally a red-only `ErrorBanner` once it
/// became clear session_screen.dart's `_QueueStatusBanner` (info/primary-
/// tinted, no error semantics) was the exact same container shape with a
/// different color — rather than let that get rebuilt as a second
/// near-duplicate later, both are now just `AppBanner` with a `variant`.
/// `success`/`warning` are included too since they cost nothing structurally
/// beyond a color/icon mapping, even though nothing in the app calls them
/// yet.
class AppBanner extends StatelessWidget {
  final String message;
  final AppBannerVariant variant;
  final String? actionLabel;
  final VoidCallback? onAction;
  final bool isActionLoading;
  final IconData? icon;

  /// Key applied to the action button, when present. Needed because at
  /// least one existing widget test asserts directly on the "Use browser
  /// instead" action's Key (connect_platform_screen.dart) — restyling that
  /// banner into AppBanner must not lose the ability to find it.
  final Key? actionKey;

  const AppBanner({
    super.key,
    required this.message,
    this.variant = AppBannerVariant.info,
    this.actionLabel,
    this.onAction,
    this.isActionLoading = false,
    this.icon,
    this.actionKey,
  });

  Color get _color {
    switch (variant) {
      case AppBannerVariant.error:
        return kRed;
      case AppBannerVariant.info:
        // Primary (pink/violet-family) accent — matches the pre-redesign
        // _QueueStatusBanner's kPrimary tint.
        return kPrimary;
      case AppBannerVariant.success:
        return kGreen;
      case AppBannerVariant.warning:
        // No dedicated "warning" token exists in theme.dart — reuse the
        // warm coral glow color rather than invent a new one for a variant
        // nothing currently calls.
        return kGlowCoral;
    }
  }

  IconData get _defaultIcon {
    switch (variant) {
      case AppBannerVariant.error:
        return Icons.error_outline;
      case AppBannerVariant.info:
        return Icons.info_outline;
      case AppBannerVariant.success:
        return Icons.check_circle_outline;
      case AppBannerVariant.warning:
        return Icons.warning_amber_outlined;
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _color;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withAlpha(kAlphaSubtle),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withAlpha(kAlphaMedium)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon ?? _defaultIcon, size: 18, color: color),
          const SizedBox(width: kSpaceSm),
          Expanded(
            child: Text(
              message,
              style: const TextStyle(fontSize: 12.5, color: kTextSecondary),
            ),
          ),
          if (actionLabel != null) ...[
            const SizedBox(width: kSpaceSm),
            isActionLoading
                ? SizedBox(
                    height: 18,
                    width: 18,
                    child: CircularProgressIndicator(strokeWidth: 2, color: color),
                  )
                : TextButton(
                    key: actionKey,
                    onPressed: onAction,
                    child: Text(actionLabel!),
                  ),
          ],
        ],
      ),
    );
  }
}
