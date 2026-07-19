// Stage C follow-up — the glow on ConnectPlatformScreen's platform rows must
// reflect live selection/connection state (which platform the user most
// recently tapped/attempted), not a static per-platform identity. This
// exercises both directions: tapping Spotify glows Spotify (not YouTube),
// tapping YouTube glows YouTube (not Spotify).
//
// No real network/App-to-App mocking needed: _selectedPlatform is set
// synchronously, before the first `await` in _connectSpotify, so the state
// change is already applied by the time tester.tap() returns — pumping once
// is enough to see it reflected. The subsequent (unmocked) HTTP call is
// harmless: TestWidgetsFlutterBinding's default HttpOverrides fakes it with
// a quick in-zone 400, so pumpAndSettle() resolves normally without needing
// runAsync or a real local server (see spotify_app_to_app_test.dart's own
// comment on this default behavior).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/features/auth/screens/connect_platform_screen.dart';

const _spotifyKey = Key('connect-spotify-button');
const _youtubeKey = Key('connect-youtube-button');

bool _isGlowing(WidgetTester tester, Key key) {
  final containers = tester.widgetList<Container>(
    find.descendant(of: find.byKey(key), matching: find.byType(Container)),
  );
  return containers.any((c) {
    final decoration = c.decoration;
    return decoration is BoxDecoration && (decoration.boxShadow?.isNotEmpty ?? false);
  });
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});
  });

  Future<void> pumpConnectScreen(WidgetTester tester) async {
    final router = GoRouter(
      initialLocation: '/connect-platform',
      routes: [
        GoRoute(path: '/connect-platform', builder: (c, s) => const ConnectPlatformScreen()),
        GoRoute(path: '/home', builder: (c, s) => const Scaffold(body: Text('HOME_PLACEHOLDER'))),
        GoRoute(path: '/', builder: (c, s) => const Scaffold(body: Text('LOGIN_PLACEHOLDER'))),
        GoRoute(
          path: '/youtube-connect',
          builder: (c, s) => const Scaffold(body: Text('YOUTUBE_WEBVIEW_PLACEHOLDER')),
        ),
      ],
    );
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();
  }

  testWidgets('neither platform glows before any selection', (tester) async {
    await pumpConnectScreen(tester);

    expect(_isGlowing(tester, _spotifyKey), isFalse);
    expect(_isGlowing(tester, _youtubeKey), isFalse);
  });

  testWidgets('tapping Connect Spotify glows Spotify, not YouTube', (tester) async {
    await pumpConnectScreen(tester);

    await tester.tap(find.byKey(_spotifyKey));
    await tester.pumpAndSettle();

    expect(_isGlowing(tester, _spotifyKey), isTrue);
    expect(_isGlowing(tester, _youtubeKey), isFalse);
  });

  testWidgets('tapping Connect YouTube Music glows YouTube, not Spotify', (tester) async {
    await pumpConnectScreen(tester);

    // A single pump (not pumpAndSettle) — the tap also pushes
    // '/youtube-connect', and letting that push transition fully settle
    // marks ConnectPlatformScreen's route offstage, which the byKey finder
    // then skips by default. One frame is enough to observe the
    // setState-driven glow change while the old route is still onstage.
    await tester.tap(find.byKey(_youtubeKey));
    await tester.pump();

    expect(_isGlowing(tester, _youtubeKey), isTrue);
    expect(_isGlowing(tester, _spotifyKey), isFalse);
  });
}
