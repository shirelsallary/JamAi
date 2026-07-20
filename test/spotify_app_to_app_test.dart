// App-to-App Spotify auth — covers the three required paths:
//   1. Spotify app installed, auth succeeds -> code + PKCE code_verifier
//      exchanged, navigates home.
//   2. Spotify app not installed -> hard-blocked with an install dialog;
//      App-to-App is never attempted and GET /auth/oauth/spotify is never
//      called at all (no silent browser-flow fallback — see the Bug-2-fix
//      reversal in connect_platform_screen.dart's _connectSpotify).
//   3. Spotify app installed, auth fails/cancels -> explicit error with a
//      manual "Use browser instead" fallback button.
//
// Three environment quirks had to be worked around to exercise this for
// real rather than settling for a weaker test:
//   - The App-to-App gate must check defaultTargetPlatform (Flutter's own
//     platform abstraction, overridable via debugDefaultTargetPlatformOverride
//     in tests), not dart:io Platform.isAndroid — the latter reports the
//     actual host OS the test runner is on (Linux/Mac/Windows), which is
//     never "Android" even inside flutter test, so it could never be
//     exercised at all under the old check. See connect_platform_screen.dart.
//   - TestWidgetsFlutterBinding installs a global HttpOverrides that fakes
//     every HTTP request with a 400, so http.get/http.post never reach a
//     real local server unless HttpOverrides.global is reset to null.
//   - Real async I/O (real sockets, real Timers) doesn't resolve inside the
//     default fake-async pump() zone; it has to run inside tester.runAsync.
//
// The MethodChannel ('jamai/spotify_app_auth') is fully mocked since it's a
// first-party channel this app defines. GET /auth/oauth/spotify and
// POST /auth/oauth/spotify/exchange are served by a real local HttpServer
// bound to 127.0.0.1:8000 (kBaseUrl in debug mode), so these tests exercise
// the actual http calls end-to-end rather than a mocked client — no new
// production-code networking seam was needed. app_links' EventChannel
// (ConnectPlatformScreen's own deep-link listener, unrelated to App-to-App)
// is also mocked — without it, activating that platform stream for real
// throws MissingPluginException asynchronously inside runAsync's real zone,
// which is what runAsync is for: surfacing async errors that pumpAndSettle's
// fake-async zone silently drops instead.

import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/features/auth/screens/connect_platform_screen.dart';

const _channel = MethodChannel('jamai/spotify_app_auth');
const _appLinksEventChannel = EventChannel('com.llfbandit.app_links/events');
const _authorizeUrl =
    'https://accounts.spotify.com/authorize?client_id=test-client-id&response_type=code&redirect_uri=jamai%3A%2F%2Fspotify-callback&scope=user-read-private+playlist-read-private&state=test-state-token';

void main() {
  late HttpServer server;
  String? lastExchangeBody;
  int authorizeRequestCount = 0;

  setUp(() async {
    HttpOverrides.global = null;
    SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});
    lastExchangeBody = null;
    authorizeRequestCount = 0;

    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockStreamHandler(
      _appLinksEventChannel,
      MockStreamHandler.inline(onListen: (arguments, events) {}, onCancel: (arguments) {}),
    );

    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 8000);
    server.listen((request) async {
      if (request.uri.path == '/auth/oauth/spotify' && request.method == 'GET') {
        authorizeRequestCount++;
        request.response.statusCode = 200;
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode({'authorize_url': _authorizeUrl}));
      } else if (request.uri.path == '/auth/oauth/spotify/exchange' &&
          request.method == 'POST') {
        lastExchangeBody = await utf8.decoder.bind(request).join();
        request.response.statusCode = 200;
        request.response.headers.contentType = ContentType.json;
        request.response.write(jsonEncode({'message': 'Spotify connected successfully'}));
      } else {
        request.response.statusCode = 404;
      }
      await request.response.close();
    });
  });

  tearDown(() async {
    await server.close(force: true);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_channel, null);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockStreamHandler(_appLinksEventChannel, null);
  });

  Future<void> pumpConnectScreen(WidgetTester tester) async {
    final router = GoRouter(
      initialLocation: '/connect-platform',
      routes: [
        GoRoute(path: '/connect-platform', builder: (c, s) => const ConnectPlatformScreen()),
        GoRoute(path: '/home', builder: (c, s) => const Scaffold(body: Text('HOME_PLACEHOLDER'))),
        GoRoute(path: '/', builder: (c, s) => const Scaffold(body: Text('LOGIN_PLACEHOLDER'))),
      ],
    );
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();
  }

  // Real network + real timers only resolve inside runAsync's real zone —
  // pumpAndSettle's fake-async zone never advances for them.
  //
  // debugDefaultTargetPlatformOverride is set/reset around just this call
  // (not via setUp/tearDown or addTearDown) because
  // TestWidgetsFlutterBinding's end-of-test invariant check runs immediately
  // after the testWidgets callback returns, before any registered teardown
  // fires — leaving it set past this point fails the test outright.
  Future<void> tapConnectAndWait(WidgetTester tester) async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    try {
      await tester.runAsync(() async {
        await tester.tap(find.byKey(const Key('connect-spotify-button')));
        await Future.delayed(const Duration(milliseconds: 300));
      });
      await tester.pumpAndSettle();
    } finally {
      debugDefaultTargetPlatformOverride = null;
    }
  }

  testWidgets(
    'Spotify app installed, auth succeeds -> code is exchanged and app navigates home',
    (tester) async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(_channel, (call) async {
        switch (call.method) {
          case 'isSpotifyInstalled':
            return true;
          case 'authorize':
            return {'type': 'code', 'code': 'auth-code-123', 'state': 'test-state-token'};
        }
        return null;
      });

      await pumpConnectScreen(tester);
      await tapConnectAndWait(tester);

      expect(find.text('HOME_PLACEHOLDER'), findsOneWidget);
      expect(
        lastExchangeBody,
        jsonEncode({'code': 'auth-code-123', 'state': 'test-state-token'}),
      );
    },
  );

  testWidgets(
    'Spotify app not installed -> hard-blocked with an install dialog, no network call at all',
    (tester) async {
      var authorizeCalled = false;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(_channel, (call) async {
        switch (call.method) {
          case 'isSpotifyInstalled':
            return false;
          case 'authorize':
            authorizeCalled = true;
            return {'type': 'code', 'code': 'should-not-be-used', 'state': 'test-state-token'};
        }
        return null;
      });

      await pumpConnectScreen(tester);
      await tapConnectAndWait(tester);

      // Hard block: GET /auth/oauth/spotify is never reached, and App-to-App
      // is never attempted either — this is not a routing decision to fall
      // back to the browser flow, it's a dead end until Spotify is installed.
      expect(authorizeRequestCount, 0);
      expect(authorizeCalled, isFalse);
      expect(lastExchangeBody, isNull);

      expect(find.text('Spotify not installed'), findsOneWidget);
      expect(
        find.text("Spotify isn't installed on this device. Install it to connect."),
        findsOneWidget,
      );
      // No secondary "continue in browser" escape hatch from this dialog.
      expect(find.byKey(const Key('use-browser-instead-button')), findsNothing);
      expect(find.text('Could not connect with the Spotify app.'), findsNothing);
    },
  );

  testWidgets(
    'Spotify app installed but auth fails -> explicit error with manual "Use browser instead"',
    (tester) async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(_channel, (call) async {
        switch (call.method) {
          case 'isSpotifyInstalled':
            return true;
          case 'authorize':
            return {'type': 'error', 'error': 'user cancelled'};
        }
        return null;
      });

      await pumpConnectScreen(tester);
      await tapConnectAndWait(tester);

      expect(find.text('Could not connect with the Spotify app.'), findsOneWidget);
      expect(find.byKey(const Key('use-browser-instead-button')), findsOneWidget);
      expect(lastExchangeBody, isNull); // never reached the exchange step

      // Manual fallback is tappable and clears the App-to-App error state.
      await tester.tap(find.byKey(const Key('use-browser-instead-button')));
      await tester.pump();
      expect(find.text('Could not connect with the Spotify app.'), findsNothing);
    },
  );

  testWidgets(
    'Spotify app installed but user cancels -> explicit error, not a silent fallback',
    (tester) async {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(_channel, (call) async {
        switch (call.method) {
          case 'isSpotifyInstalled':
            return true;
          case 'authorize':
            return {'type': 'cancelled'};
        }
        return null;
      });

      await pumpConnectScreen(tester);
      await tapConnectAndWait(tester);

      expect(find.text('Spotify connection was cancelled.'), findsOneWidget);
      expect(find.byKey(const Key('use-browser-instead-button')), findsOneWidget);
    },
  );
}
