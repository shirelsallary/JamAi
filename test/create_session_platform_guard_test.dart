// Section 0 platform-guard fix — CreateSessionScreen must never be reachable
// without a connected platform: it now redirects to /connect-platform
// whenever GET /auth/me doesn't confirm one, instead of rendering the JAM
// creation form with an inline "connect first" banner.
//
// Own file (not navigation_test.dart) because both cases below need a real
// GET /auth/me response — same real-local-HttpServer + runAsync pattern as
// spotify_playback_retry_test.dart (TestWidgetsFlutterBinding otherwise fakes
// all HTTP with 400, and HttpOverrides.global is a process-wide static, so
// mixing this with tests that rely on the default fake-400 behavior in the
// same file is fragile).

import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/features/session/screens/create_session_screen.dart';

void main() {
  late HttpServer server;
  late Map<String, dynamic> meResponse;

  setUp(() async {
    HttpOverrides.global = null;
    SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});
    meResponse = {'platform': 'spotify', 'platform_token': 'tok'};

    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 8000);
    server.listen((request) async {
      if (request.uri.path == '/auth/me') {
        request.response.statusCode = 200;
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(meResponse));
      } else {
        request.response.statusCode = 404;
      }
      await request.response.close();
    });
  });

  tearDown(() async {
    await server.close(force: true);
  });

  Future<void> pumpCreateSession(WidgetTester tester) async {
    final router = GoRouter(
      initialLocation: '/session/create',
      routes: [
        GoRoute(
          path: '/session/create',
          builder: (c, s) => const CreateSessionScreen(),
        ),
        GoRoute(
          path: '/connect-platform',
          builder: (c, s) => const Scaffold(body: Text('CONNECT_PLATFORM_PLACEHOLDER')),
        ),
      ],
    );
    await tester.runAsync(() async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await Future.delayed(const Duration(milliseconds: 300));
    });
    await tester.pumpAndSettle();
  }

  testWidgets(
    'platform connected -> renders the JAM creation form',
    (tester) async {
      await pumpCreateSession(tester);

      expect(find.text('CONNECT_PLATFORM_PLACEHOLDER'), findsNothing);
      expect(find.text('Create JAM Session'), findsOneWidget);
    },
  );

  testWidgets(
    'no platform connected -> redirects to /connect-platform instead of '
    'rendering the JAM creation form',
    (tester) async {
      // Legitimate "logged in, nothing connected" response — same shape
      // UserResponse sends for a user who never connected anything.
      meResponse = {'platform': null};

      await pumpCreateSession(tester);

      expect(find.text('CONNECT_PLATFORM_PLACEHOLDER'), findsOneWidget);
      expect(find.text('Create JAM Session'), findsNothing);
    },
  );
}
