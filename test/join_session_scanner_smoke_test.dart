// Stage E — smoke test for JoinSessionScreen with the new mobile_scanner
// integration. See the Stage E report for what this can and cannot cover:
// actual camera/barcode-detection behavior needs a real device (no
// automated substitute attempted here, matching the standard set for the
// YouTube IFrame Player work earlier in this project).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/features/session/screens/join_session_screen.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({'token': 'fake-test-token'});
  });

  Future<void> pumpJoinScreen(WidgetTester tester, {String? initialCode}) async {
    final router = GoRouter(
      initialLocation: '/session/join',
      routes: [
        GoRoute(
          path: '/session/join',
          builder: (c, s) => JoinSessionScreen(initialCode: initialCode),
        ),
        GoRoute(path: '/', builder: (c, s) => const Scaffold(body: Text('LOGIN_PLACEHOLDER'))),
        GoRoute(
          path: '/connect-platform',
          builder: (c, s) => const Scaffold(body: Text('CONNECT_PLACEHOLDER')),
        ),
      ],
    );
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();
  }

  testWidgets('renders without crashing, camera errors gracefully degrade to manual entry',
      (tester) async {
    await pumpJoinScreen(tester);

    // No real camera platform channel exists in this environment — the
    // MobileScanner widget is expected to surface that as a
    // MobileScannerException via errorBuilder rather than crash, which is
    // exactly the fallback path a real permission-denied/unsupported-device
    // user would also hit. This test's real assertion is "the screen still
    // renders its manual-entry UI regardless."
    expect(find.byKey(const Key('qr-scanner-view')), findsOneWidget);
    expect(find.text('OR ENTER CODE'), findsOneWidget);
    expect(find.text('Join'), findsOneWidget);
  });

  testWidgets('deep-link initialCode still pre-fills the manual code field', (tester) async {
    await pumpJoinScreen(tester, initialCode: 'ab12cd');

    final field = tester.widget<TextField>(find.byType(TextField).first);
    expect(field.controller?.text, 'AB12CD');
  });
}
