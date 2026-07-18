// Reconnect entry point — Step A (playlist-read-private scope fix) report
// found no way back to ConnectPlatformScreen for an already-connected user:
// every route that checks platform_token (login/register/splash) treats a
// non-empty token as fully connected and routes past that screen entirely.
// This adds a minimal, always-visible entry point on HomeScreen so an
// already-connected user can re-run OAuth and pick up newly added scopes.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/features/home/screens/home_screen.dart';

void main() {
  Future<GoRouter> pumpHomeScreen(WidgetTester tester) async {
    final router = GoRouter(
      initialLocation: '/home',
      routes: [
        GoRoute(path: '/home', builder: (context, state) => const HomeScreen()),
        GoRoute(
          path: '/connect-platform',
          builder: (context, state) =>
              const Scaffold(body: Text('CONNECT_PLATFORM_PLACEHOLDER')),
        ),
      ],
    );
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();
    return router;
  }

  testWidgets(
    'Manage Spotify Connection button reaches ConnectPlatformScreen even '
    'though HomeScreen never checked platform_token before',
    (tester) async {
      // No 'has connected before' flag exists anywhere in this app's storage
      // model — the point of this test is that the button is reachable
      // unconditionally, not gated on any stored connection state.
      SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});

      await pumpHomeScreen(tester);

      expect(find.byKey(const Key('manage-spotify-connection-button')), findsOneWidget);

      await tester.tap(find.byKey(const Key('manage-spotify-connection-button')));
      await tester.pumpAndSettle();

      expect(find.text('CONNECT_PLATFORM_PLACEHOLDER'), findsOneWidget);
    },
  );
}
