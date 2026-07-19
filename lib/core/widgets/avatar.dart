import 'package:flutter/material.dart';
import '../theme.dart';

/// Gradient circle avatar — the pink-purple gradient fill used for the
/// user avatar (Home's top bar) and jammer-stack icons (session history
/// cards, Now Playing's contributor list) in the mockup. Shows initials if
/// provided, otherwise a generic person icon.
class Avatar extends StatelessWidget {
  final double size;
  final String? initials;
  final Border? border;

  const Avatar({
    super.key,
    this.size = 40,
    this.initials,
    this.border,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: const LinearGradient(
          colors: kPrimaryGradient,
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        border: border,
      ),
      alignment: Alignment.center,
      child: initials != null && initials!.isNotEmpty
          ? Text(
              initials!.length > 2 ? initials!.substring(0, 2) : initials!,
              style: TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.bold,
                fontSize: size * 0.4,
              ),
            )
          : Icon(Icons.person, color: Colors.white, size: size * 0.5),
    );
  }
}
