import 'dart:io';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'core/theme.dart';
import 'core/router.dart';

/// Accepts self-signed / untrusted certs so the desktop app can reach a
/// local backend over HTTPS during development. NEVER enabled outside
/// debug mode — see the kDebugMode guard in main().
class _DevHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    return super.createHttpClient(context)
      ..badCertificateCallback = (cert, host, port) => true;
  }
}

void main() {
  if (kDebugMode) {
    HttpOverrides.global = _DevHttpOverrides();
  }
  runApp(const JamAiApp());
}

class JamAiApp extends StatelessWidget {
  const JamAiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'JAM AI',
      theme: jamAiTheme,
      debugShowCheckedModeBanner: false,
      routerConfig: appRouter,
    );
  }
}
