// Bug 2 "also fix" — ConnectPlatformScreen's YouTube button used to show a
// blocking _showYoutubeUnsupportedDialog() even though YouTubeWebViewScreen
// already existed and worked; it was simply unreachable. This confirms the
// button now navigates instead of showing that dialog.
//
// The real YouTubeWebViewScreen route is swapped for a placeholder here: it
// constructs a native WebViewController in initState, which needs platform
// channels this widget-test environment doesn't provide. What's under test
// is navigation behavior (did tapping the button take you to that route),
// not the WebView screen's own rendering.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/features/auth/screens/connect_platform_screen.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});
  });

  testWidgets(
    'tapping Connect YouTube Music navigates to YouTubeWebViewScreen, not a dialog',
    (tester) async {
      final router = GoRouter(
        initialLocation: '/connect-platform',
        routes: [
          GoRoute(
            path: '/connect-platform',
            builder: (context, state) => const ConnectPlatformScreen(),
          ),
          GoRoute(
            path: '/youtube-connect',
            builder: (context, state) =>
                const Scaffold(body: Text('YOUTUBE_WEBVIEW_PLACEHOLDER')),
          ),
        ],
      );

      await tester.pumpWidget(MaterialApp.router(routerConfig: router));
      await tester.pumpAndSettle();

      expect(find.text('Connect YouTube Music'), findsOneWidget);

      await tester.tap(find.byKey(const Key('connect-youtube-button')));
      await tester.pumpAndSettle();

      expect(find.byType(AlertDialog), findsNothing); // old blocking behavior gone
      expect(find.text('YOUTUBE_WEBVIEW_PLACEHOLDER'), findsOneWidget);
    },
  );
}
