import 'package:flutter/material.dart';
import '../theme.dart';

/// Which streaming platform a badge/status widget refers to.
enum AppPlatform { spotify, youtube }

/// Read-only status badge showing which platform is connected/active —
/// consolidates the two near-identical private `_PlatformBadge` widgets
/// previously duplicated in create_session_screen.dart ("Playing via") and
/// join_session_screen.dart ("Joining via"). The default label covers both
/// call sites' generic case; pass [label] to reproduce a screen-specific
/// prefix like "Joining via Spotify".
///
/// This is deliberately NOT the same component as ConnectPlatformScreen's
/// `_PlatformConnectButton` — that one is an interactive "choose a
/// platform" selector where only one of two rows is glowing/selected at a
/// time; this one only ever displays a single already-decided platform, so
/// it always renders in its "active" glow state. Per the audit, these two
/// are semantically different (selector vs. status display) and are not
/// merged into one widget.
class PlatformBadge extends StatelessWidget {
  final AppPlatform platform;
  final String? label;
  final bool compact;

  const PlatformBadge({
    super.key,
    required this.platform,
    this.label,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    final isSpotify = platform == AppPlatform.spotify;
    final color = isSpotify ? kGreen : kYouTubeRed;
    final text = label ?? (isSpotify ? 'Spotify' : 'YouTube Music');

    return Container(
      padding: compact
          ? const EdgeInsets.symmetric(horizontal: kSpaceMd, vertical: kSpaceSm + 2)
          : const EdgeInsets.all(kSpaceMd),
      decoration: BoxDecoration(
        color: color.withAlpha(kAlphaSoft),
        borderRadius: BorderRadius.circular(compact ? kRadiusPill : kRadiusSm),
        border: Border.all(color: color, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: color.withAlpha(kAlphaMedium),
            blurRadius: 12,
            spreadRadius: 1,
          ),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: compact ? 10 : 12,
            height: compact ? 10 : 12,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: kSpaceSm),
          Text(text, style: TextStyle(fontWeight: FontWeight.bold, color: color)),
        ],
      ),
    );
  }
}
