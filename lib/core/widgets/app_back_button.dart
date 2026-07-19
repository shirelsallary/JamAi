import 'package:flutter/material.dart';
import '../theme.dart';

/// Centralizes the visual treatment of the app's back chevron — a
/// white/near-white `Icons.arrow_back_ios` icon — that was previously
/// copy-pasted at every AppBar `leading:` call site.
///
/// Deliberately does NOT decide whether a back button should be shown, or
/// what pressing it does. Per the audit, screens diverge in that logic on
/// purpose (canPop-conditional on RegisterScreen/ConnectPlatformScreen/
/// CreateSessionScreen/JoinSessionScreen, an always-present `go('/home')`
/// on SessionScreen, entirely absent on ExportScreen/HomeScreen/LoginScreen)
/// — only the visual part is meant to be centralized here. Each screen
/// keeps deciding whether to place this in `leading:` at all, and supplies
/// its own `onPressed`.
class AppBackButton extends StatelessWidget {
  final VoidCallback onPressed;

  const AppBackButton({super.key, required this.onPressed});

  @override
  Widget build(BuildContext context) {
    return IconButton(
      icon: const Icon(Icons.arrow_back_ios, color: kTextPrimary),
      onPressed: onPressed,
    );
  }
}
