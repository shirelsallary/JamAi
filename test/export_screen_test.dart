// Stage G — ExportScreen. Real local HttpServer on port 8000 (same pattern
// as spotify_playback_retry_test.dart / spotify_app_to_app_test.dart):
// HttpOverrides.global reset to null, driven inside tester.runAsync since
// TestWidgetsFlutterBinding's fake-async zone never resolves real sockets.

import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/features/export/screens/export_screen.dart';

void main() {
  late HttpServer server;
  late int exportStatusCode;
  late Map<String, dynamic> exportBody;

  setUp(() async {
    HttpOverrides.global = null;
    SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});
    exportStatusCode = 200;
    exportBody = {'playlist_url': 'https://open.spotify.com/playlist/abc123', 'track_count': 7};

    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 8000);
    server.listen((request) async {
      if (request.uri.path.endsWith('/export') && request.method == 'POST') {
        request.response.statusCode = exportStatusCode;
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode(exportBody));
      } else {
        request.response.statusCode = 404;
      }
      await request.response.close();
    });
  });

  tearDown(() async {
    await server.close(force: true);
  });

  Future<void> pumpExportScreen(WidgetTester tester) async {
    final router = GoRouter(
      initialLocation: '/export/test-session-id',
      routes: [
        GoRoute(
          path: '/export/:id',
          builder: (c, s) => ExportScreen(sessionId: s.pathParameters['id']!),
        ),
        GoRoute(path: '/home', builder: (c, s) => const Scaffold(body: Text('HOME_PLACEHOLDER'))),
        GoRoute(path: '/', builder: (c, s) => const Scaffold(body: Text('LOGIN_PLACEHOLDER'))),
      ],
    );
    await tester.runAsync(() async {
      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await Future.delayed(const Duration(milliseconds: 300));
    });
    await tester.pumpAndSettle();
  }

  testWidgets('terminal screen has no back button (automaticallyImplyLeading preserved)',
      (tester) async {
    await pumpExportScreen(tester);

    expect(find.byType(BackButton), findsNothing);
    final appBar = tester.widget<AppBar>(find.byType(AppBar));
    expect(appBar.automaticallyImplyLeading, isFalse);
  });

  testWidgets('successful export shows track count, playlist URL, and action buttons',
      (tester) async {
    await pumpExportScreen(tester);

    expect(find.textContaining('JAM Saved'), findsOneWidget);
    expect(find.text('7 tracks saved to your playlist'), findsOneWidget);
    expect(find.text('https://open.spotify.com/playlist/abc123'), findsOneWidget);
    expect(find.text('Open Playlist'), findsOneWidget);
    expect(find.text('Share link'), findsNothing);
  });

  testWidgets('failed export shows the error state with a working Try Again button',
      (tester) async {
    exportStatusCode = 422;
    await pumpExportScreen(tester);

    expect(find.text('Export failed. Session may already be exported.'), findsOneWidget);
    expect(find.text('Try Again'), findsOneWidget);
    expect(find.text('Go to Home'), findsOneWidget);

    exportStatusCode = 200;
    await tester.runAsync(() async {
      await tester.tap(find.text('Try Again'));
      await Future.delayed(const Duration(milliseconds: 300));
    });
    await tester.pumpAndSettle();

    expect(find.textContaining('JAM Saved'), findsOneWidget);
  });

  testWidgets('Go to Home navigates home from the error state', (tester) async {
    exportStatusCode = 422;
    await pumpExportScreen(tester);

    await tester.tap(find.text('Go to Home'));
    await tester.pumpAndSettle();

    expect(find.text('HOME_PLACEHOLDER'), findsOneWidget);
  });
}
