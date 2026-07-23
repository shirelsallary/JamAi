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

  // Simulates the real entry point (SessionScreen pushes '/export/:id', see
  // session_screen.dart's _endSession) so a failed export has an underlying
  // route to pop back to, same as production.
  Future<void> pumpExportScreenReachedViaPush(WidgetTester tester) async {
    final router = GoRouter(
      initialLocation: '/root',
      routes: [
        GoRoute(
          path: '/root',
          builder: (c, s) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () => c.push('/export/test-session-id'),
                child: const Text('ROOT_PLACEHOLDER'),
              ),
            ),
          ),
        ),
        GoRoute(
          path: '/export/:id',
          builder: (c, s) => ExportScreen(sessionId: s.pathParameters['id']!),
        ),
        GoRoute(path: '/home', builder: (c, s) => const Scaffold(body: Text('HOME_PLACEHOLDER'))),
        GoRoute(path: '/', builder: (c, s) => const Scaffold(body: Text('LOGIN_PLACEHOLDER'))),
      ],
    );

    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();

    // The tap, the pump that finishes the push transition (mounting
    // ExportScreen and firing its initState's real http.post), AND the real
    // wait for that call to resolve must all happen inside the SAME
    // runAsync call — a Future's real I/O is bound to whichever zone it was
    // *started* in, not whatever zone later awaits it, so starting the real
    // HTTP call outside runAsync (e.g. via a plain tester.pump() beforehand)
    // means it can never resolve no matter how long a later runAsync waits.
    await tester.runAsync(() async {
      await tester.tap(find.text('ROOT_PLACEHOLDER'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400)); // finish the push transition
      await Future.delayed(const Duration(milliseconds: 400)); // let the real POST resolve
    });

    // Discrete pumps rather than pumpAndSettle() to reflect the now-resolved
    // state — pumpAndSettle's own animation-quiescence wait doesn't play
    // well with this harness's page-transition timing. 10x100ms comfortably
    // covers the ~600ms the pop transition needs to fully finish.
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
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

  testWidgets(
    'failed export pops back to the caller (e.g. SessionScreen) instead of '
    'showing a separate error screen — no error screen/dialog is ever shown',
    (tester) async {
      exportStatusCode = 422;
      await pumpExportScreenReachedViaPush(tester);

      // Popped back to whatever pushed this route — not stuck here, and
      // no error UI of any kind was ever shown on this screen.
      expect(find.text('ROOT_PLACEHOLDER'), findsOneWidget);
      expect(find.textContaining('JAM Saved'), findsNothing);
      expect(find.text('Export failed. Session may already be exported.'), findsNothing);
      expect(find.byType(ExportScreen), findsNothing);
    },
  );

  testWidgets(
    'successful export is unaffected — still lands on the "JAM Saved!" success '
    'screen when reached via push (same as the real SessionScreen entry point)',
    (tester) async {
      await pumpExportScreenReachedViaPush(tester);

      expect(find.textContaining('JAM Saved'), findsOneWidget);
      expect(find.text('Open Playlist'), findsOneWidget);
    },
  );
}
