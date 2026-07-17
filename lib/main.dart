import 'dart:async';
import 'dart:io';
import 'package:app_links/app_links.dart';
import 'package:flutter/foundation.dart' show kDebugMode;
import 'package:flutter/material.dart';
import 'core/deep_link_utils.dart';
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

class JamAiApp extends StatefulWidget {
  const JamAiApp({super.key});

  @override
  State<JamAiApp> createState() => _JamAiAppState();
}

class _JamAiAppState extends State<JamAiApp> {
  AppLinks? _appLinks;
  StreamSubscription<Uri>? _linkSubscription;

  @override
  void initState() {
    super.initState();
    _listenForJoinLinks();
  }

  // App-level (not screen-scoped) deep-link handling for jamai://join/{code}
  // — unlike the Spotify callback (ConnectPlatformScreen, Bug 2), this covers
  // BOTH the "warm" case (app already running, via the stream) AND the "cold
  // start" case (app launched by tapping/scanning the link, via
  // getInitialLink()). Cold start matters much more here: there is no in-app
  // QR scanner (mobile_scanner/qr_flutter are declared in pubspec.yaml but
  // unused anywhere in this app), so an external scanner app opening this
  // link is the ONLY way a join link is ever actually followed — it would
  // almost always be hitting a not-yet-running app.
  Future<void> _listenForJoinLinks() async {
    try {
      _appLinks = AppLinks();

      final initial = await _appLinks!.getInitialLink();
      if (initial != null) _handleDeepLink(initial);

      _linkSubscription = _appLinks!.uriLinkStream.listen(
        _handleDeepLink,
        onError: (_) {},
      );
    } catch (_) {
      // no deep-link support on this platform — joining still works by
      // typing the code manually on JoinSessionScreen.
    }
  }

  void _handleDeepLink(Uri uri) {
    final code = parseJoinCode(uri);
    if (code != null) {
      appRouter.go('/session/join?code=$code');
    }
  }

  @override
  void dispose() {
    _linkSubscription?.cancel();
    super.dispose();
  }

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
