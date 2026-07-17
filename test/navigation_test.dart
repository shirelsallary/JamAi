// Bug 1 fix — widget tests for back-button reachability.
//
// Screens are pumped inside a bare Navigator (with or without a dummy route
// beneath them) rather than the real GoRouter/network stack, since the thing
// under test — `Navigator.canPop(context)` driving `leading:` — is a plain
// Flutter Navigator mechanism, independent of go_router or the backend.
// `reachedViaPush: true` mirrors context.push (a route sits beneath, so
// canPop is true); `reachedViaPush: false` mirrors context.go (the whole
// stack is replaced, so canPop is false).
//
// Screens that call AuthService.getToken()/getMe() in initState need a
// non-null token in SharedPreferences, otherwise they call context.go('/')
// on a null token — which throws with no GoRouter present. The token being
// "fake" is fine: AuthService.getMe swallows the resulting network failure
// and returns null, which these screens already handle gracefully (they're
// not what's under test here).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/features/auth/screens/connect_platform_screen.dart';
import 'package:jam_ai_app/features/auth/screens/register_screen.dart';
import 'package:jam_ai_app/features/export/screens/export_screen.dart';
import 'package:jam_ai_app/features/home/screens/home_screen.dart';
import 'package:jam_ai_app/features/session/screens/create_session_screen.dart';
import 'package:jam_ai_app/features/session/screens/join_session_screen.dart';

Future<void> pumpScreen(
  WidgetTester tester,
  Widget screen, {
  required bool reachedViaPush,
}) async {
  final navigatorKey = GlobalKey<NavigatorState>();
  await tester.pumpWidget(MaterialApp(
    // Not MaterialApp.navigatorKey — that would also apply to MaterialApp's
    // own internally-managed Navigator, conflicting with the explicit one
    // below (duplicate GlobalKey -> framework assertion failure).
    home: Navigator(
      key: navigatorKey,
      onGenerateRoute: (_) => MaterialPageRoute(
        builder: (_) => const Scaffold(body: Text('root')),
      ),
    ),
  ));
  await tester.pumpAndSettle();

  if (reachedViaPush) {
    navigatorKey.currentState!.push(MaterialPageRoute(builder: (_) => screen));
  } else {
    navigatorKey.currentState!
        .pushReplacement(MaterialPageRoute(builder: (_) => screen));
  }
  await tester.pumpAndSettle();
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});
  });

  group('push-reached screens render a working back button', () {
    testWidgets('RegisterScreen (Login -> Register is now push)', (tester) async {
      await pumpScreen(tester, const RegisterScreen(), reachedViaPush: true);
      expect(find.byIcon(Icons.arrow_back_ios), findsOneWidget);
    });

    testWidgets('CreateSessionScreen (Home -> Create is now push)', (tester) async {
      await pumpScreen(tester, const CreateSessionScreen(), reachedViaPush: true);
      expect(find.byIcon(Icons.arrow_back_ios), findsOneWidget);
    });

    testWidgets('JoinSessionScreen (Home -> Join is now push)', (tester) async {
      await pumpScreen(tester, const JoinSessionScreen(), reachedViaPush: true);
      expect(find.byIcon(Icons.arrow_back_ios), findsOneWidget);
    });

    testWidgets(
      'ConnectPlatformScreen reached via push (e.g. the "connect first" '
      'banner on CreateSessionScreen/JoinSessionScreen)',
      (tester) async {
        await pumpScreen(tester, const ConnectPlatformScreen(), reachedViaPush: true);
        expect(find.byIcon(Icons.arrow_back_ios), findsOneWidget);
      },
    );
  });

  group('go-reached screens (state transitions) show no back button', () {
    testWidgets(
      'ConnectPlatformScreen reached via go (post-registration/login/splash) '
      'shows no back button — same conditional pattern, different reachability',
      (tester) async {
        await pumpScreen(tester, const ConnectPlatformScreen(), reachedViaPush: false);
        expect(find.byIcon(Icons.arrow_back_ios), findsNothing);
      },
    );

    testWidgets('HomeScreen (post-login/post-logout landing) has no back button',
        (tester) async {
      await pumpScreen(tester, const HomeScreen(), reachedViaPush: false);
      expect(find.byIcon(Icons.arrow_back_ios), findsNothing);
      expect(find.byIcon(Icons.arrow_back), findsNothing);
    });

    testWidgets(
      'ExportScreen never shows a back button, by design (automaticallyImplyLeading: '
      'false) — verified this is NOT accidentally a regression by pumping it WITH a '
      'poppable stack beneath it, per the explicit instruction to leave this one alone',
      (tester) async {
        await pumpScreen(
          tester,
          const ExportScreen(sessionId: 'test-session-id'),
          reachedViaPush: true,
        );
        expect(find.byIcon(Icons.arrow_back_ios), findsNothing);
        expect(find.byIcon(Icons.arrow_back), findsNothing);
      },
    );
  });
}
