import 'package:flutter/material.dart';
import '../theme.dart';

/// Warning banner shown in place of [PlatformBadge] when the user has no
/// connected platform yet — consolidates the two near-identical private
/// `_NoPlatformConnectedBanner` widgets previously duplicated in
/// create_session_screen.dart and join_session_screen.dart (which differed
/// only in text alignment).
class NoPlatformConnectedBanner extends StatelessWidget {
  final VoidCallback onConnect;
  final TextAlign textAlign;

  const NoPlatformConnectedBanner({
    super.key,
    required this.onConnect,
    this.textAlign = TextAlign.start,
  });

  @override
  Widget build(BuildContext context) {
    final centered = textAlign == TextAlign.center;
    return Container(
      padding: const EdgeInsets.all(kSpaceMd),
      decoration: BoxDecoration(
        color: kRed.withAlpha(kAlphaSoft),
        borderRadius: BorderRadius.circular(kRadiusSm),
        border: Border.all(color: kRed, width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: centered ? CrossAxisAlignment.center : CrossAxisAlignment.start,
        children: [
          Text(
            "You haven't connected a platform yet.",
            textAlign: textAlign,
            style: const TextStyle(color: kRed, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: kSpaceSm),
          TextButton(
            onPressed: onConnect,
            child: const Text('Connect Spotify or YouTube Music'),
          ),
        ],
      ),
    );
  }
}
