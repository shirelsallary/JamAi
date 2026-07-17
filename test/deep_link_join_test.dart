// Item 3 fix — jamai://join/{code} deep link.
//
// Two seams are tested separately, same technique as
// connect_platform_youtube_test.dart:
//   1. parseJoinCode is a pure function (no platform channels) — tested
//      directly against a variety of URIs.
//   2. The router wiring (query param -> JoinSessionScreen.initialCode ->
//      TextField prefill) — tested by navigating a local GoRouter straight to
//      '/session/join?code=...', which is exactly what main.dart's
//      _handleDeepLink does after parsing. The actual AppLinks stream/
//      getInitialLink() platform channel itself isn't exercised here (same
//      constraint as the Spotify deep-link tests — no platform channels in
//      this widget-test environment).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/core/deep_link_utils.dart';
import 'package:jam_ai_app/features/session/screens/join_session_screen.dart';

void main() {
  group('parseJoinCode', () {
    test('extracts and uppercases the code from a valid join link', () {
      expect(parseJoinCode(Uri.parse('jamai://join/abc123')), 'ABC123');
    });

    test('returns null for the wrong scheme', () {
      expect(parseJoinCode(Uri.parse('https://join/abc123')), isNull);
    });

    test('returns null for the wrong host (e.g. the Spotify callback link)', () {
      expect(
        parseJoinCode(Uri.parse('jamai://spotify-callback?code=x&state=y')),
        isNull,
      );
    });

    test('returns null when there is no code segment', () {
      expect(parseJoinCode(Uri.parse('jamai://join/')), isNull);
      expect(parseJoinCode(Uri.parse('jamai://join')), isNull);
    });
  });

  group('deep link -> JoinSessionScreen wiring', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});
    });

    testWidgets(
      'navigating to /session/join?code=... pre-fills the join code field',
      (tester) async {
        final router = GoRouter(
          initialLocation: '/session/join?code=ABC123',
          routes: [
            GoRoute(
              path: '/session/join',
              builder: (context, state) => JoinSessionScreen(
                initialCode: state.uri.queryParameters['code'],
              ),
            ),
          ],
        );

        await tester.pumpWidget(MaterialApp.router(routerConfig: router));
        await tester.pumpAndSettle();

        expect(find.widgetWithText(TextField, 'ABC123'), findsOneWidget);

        // Pre-filled + a platform already resolved (mock token, network call
        // fails gracefully and is treated as "not connected") means the
        // field itself is ready to submit — Join button state depends on
        // platform connection, not exercised further here.
      },
    );
  });
}
