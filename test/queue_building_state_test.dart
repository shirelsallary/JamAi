// Queue-building loading state (session_screen.dart) — the backend has no
// distinct "still building" queue_build_status (models.py only allows
// 'full'/'partial'/'empty'; a session that just got created and one that
// finished building with zero real matches both report "empty"). Right after
// session creation, GET /queue/{id} returns queue_build_status="empty" with
// 0 tracks while optimize_queue's background build is still running — the
// screen must show a clear "still working" state instead of a bare
// "Queue is empty", which reads as broken.
//
// Same real-local-HttpServer + runAsync pattern as spotify_playback_retry_test.dart
// (TestWidgetsFlutterBinding otherwise fakes all HTTP with 400).

import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/features/session/screens/session_screen.dart';

void main() {
  late HttpServer server;
  late Map<String, dynamic> queuePayload;

  setUp(() async {
    HttpOverrides.global = null;
    SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});

    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 8000);
    server.listen((request) async {
      if (request.uri.path.startsWith('/queue/') && request.method == 'GET') {
        request.response.statusCode = 200;
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(queuePayload));
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
      ],
    );
    await tester.runAsync(() async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await Future.delayed(const Duration(milliseconds: 400));
    });
    // pump(), not pumpAndSettle() — the "still building" state renders an
    // indeterminate CircularProgressIndicator, which animates forever and
    // would make pumpAndSettle() time out waiting for it to stop.
    await tester.pump();
  }

  testWidgets(
    'freshly-created session (queue_build_status=empty, no tracks yet) shows '
    'a "building" message with a spinner, not a bare "Queue is empty"',
    (tester) async {
      queuePayload = {
        'tracks': [],
        'queue_build_status': 'empty',
        'effective_threshold': null,
        'host_platform': 'spotify',
      };

      await pumpSessionScreen(tester);

      expect(
        find.text("Building your queue... this'll just take a few seconds"),
        findsOneWidget,
      );
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.text('Queue is empty'), findsNothing);
      // The generic "couldn't find any matching songs yet" banner would be
      // redundant on top of the dedicated loading state above.
      expect(
        find.textContaining("couldn't find any matching songs"),
        findsNothing,
      );
    },
  );

  testWidgets(
    'queue already has tracks -> no building message, normal queue renders',
    (tester) async {
      queuePayload = {
        'tracks': [
          {
            'id': 'q1',
            'track_id': 'yt_track_1',
            'platform': 'youtube',
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

      await pumpSessionScreen(tester);

      expect(
        find.text("Building your queue... this'll just take a few seconds"),
        findsNothing,
      );
      expect(find.text('Test Song'), findsOneWidget);
    },
  );
}
