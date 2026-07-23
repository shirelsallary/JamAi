// Spotify real-playback retry UI (session_screen.dart) — the device-must-be-
// active constraint is a routine, expected condition, so the banner + Retry
// button need to actually work, not just exist.
//
// Same environment workarounds as spotify_app_to_app_test.dart: real local
// HttpServer (HttpOverrides.global reset to null; TestWidgetsFlutterBinding
// otherwise fakes all HTTP with 400), driven inside tester.runAsync (real
// sockets/timers don't resolve inside pumpAndSettle's fake-async zone). The
// WebSocket connection this screen also opens (_connectWebSocket) is left
// unhandled by the stub server — it fails to upgrade, which SessionScreen
// already tolerates via its onError handler, same as it would with no
// backend reachable at all.

import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/features/session/screens/session_screen.dart';

const _queuePayload = {
  'tracks': [
    {
      'id': 'q1',
      'track_id': 'spotify_track_1',
      'platform': 'spotify',
      'title': 'Test Song',
      'artist': 'Test Artist',
      'duration_ms': 200000,
      'weight_score': 0.9,
      'confidence': 'high',
      'playlist_overlap_count': 0,
      'shared_artist_count': 0,
      'position': 0,
    },
  ],
  'queue_build_status': 'full',
  'effective_threshold': 0.8,
  'host_platform': 'spotify',
};

void main() {
  late HttpServer server;
  late String playResponseStatus;
  late String? playResponseReason;

  setUp(() async {
    HttpOverrides.global = null;
    SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});
    playResponseStatus = 'no_active_device';
    playResponseReason = null;

    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 8000);
    server.listen((request) async {
      if (request.uri.path.startsWith('/queue/') && request.uri.path.endsWith('/play') &&
          request.method == 'POST') {
        request.response.statusCode = 200;
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode({
          'status': playResponseStatus,
          'reason': playResponseReason,
        }));
      } else if (request.uri.path.startsWith('/queue/') && request.method == 'GET') {
        request.response.statusCode = 200;
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(_queuePayload));
      } else {
        request.response.statusCode = 404;
      }
      await request.response.close();
    });
  });

  tearDown(() async {
    await server.close(force: true);
  });

  Future<void> pumpSessionScreen(WidgetTester tester) async {
    final router = GoRouter(
      initialLocation: '/session/test-session-id',
      routes: [
        GoRoute(
          path: '/session/:id',
          builder: (c, s) => SessionScreen(sessionId: s.pathParameters['id']!),
        ),
        GoRoute(path: '/home', builder: (c, s) => const Scaffold(body: Text('HOME_PLACEHOLDER'))),
        GoRoute(path: '/', builder: (c, s) => const Scaffold(body: Text('LOGIN_PLACEHOLDER'))),
        GoRoute(
          path: '/connect-platform',
          builder: (c, s) => const Scaffold(body: Text('CONNECT_PLATFORM_PLACEHOLDER')),
        ),
      ],
    );
    await tester.runAsync(() async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      // Real HTTP round trip (queue load, then the on-mount play attempt)
      // needs real time to resolve inside runAsync's real zone.
      await Future.delayed(const Duration(milliseconds: 400));
    });
    await tester.pumpAndSettle();
  }

  testWidgets(
    'no active Spotify device -> banner shown with a working Retry button',
    (tester) async {
      await pumpSessionScreen(tester);

      expect(find.byKey(const Key('spotify-playback-banner')), findsOneWidget);
      expect(
        find.text('Open Spotify on your phone and play (or pause) any track, then retry.'),
        findsOneWidget,
      );

      // Tapping Retry re-calls the same endpoint; this time simulate success.
      playResponseStatus = 'playing';
      await tester.runAsync(() async {
        await tester.tap(find.byKey(const Key('retry-playback-button')));
        await Future.delayed(const Duration(milliseconds: 300));
      });
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('spotify-playback-banner')), findsNothing);
    },
  );

  testWidgets(
    'playback already active -> no banner shown at all',
    (tester) async {
      playResponseStatus = 'playing';

      await pumpSessionScreen(tester);

      expect(find.byKey(const Key('spotify-playback-banner')), findsNothing);
    },
  );

  testWidgets(
    'Spotify reauth required (Fix 1) -> banner with a Reconnect action, not Retry',
    (tester) async {
      playResponseStatus = 'error';
      playResponseReason = 'SPOTIFY_REAUTH_REQUIRED';

      await pumpSessionScreen(tester);

      expect(find.byKey(const Key('spotify-playback-banner')), findsOneWidget);
      expect(find.byKey(const Key('retry-playback-button')), findsNothing);
      expect(find.byKey(const Key('reconnect-spotify-button')), findsOneWidget);
      expect(
        find.text('Your Spotify connection expired. Reconnect to keep playback working.'),
        findsOneWidget,
      );

      // Tapping it goes to the existing "Manage Spotify Connection" reconnect
      // entry point (ConnectPlatformScreen) rather than retrying the same
      // dead refresh token.
      await tester.tap(find.byKey(const Key('reconnect-spotify-button')));
      await tester.pumpAndSettle();

      expect(find.text('CONNECT_PLATFORM_PLACEHOLDER'), findsOneWidget);
    },
  );
}
