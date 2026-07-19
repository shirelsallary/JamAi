// Stage E — SessionQrScreen. qr_flutter's QrImageView encodes purely in
// Dart (no platform channel), so this is fully automatable, unlike the
// camera-scanner side of this stage.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:qr_flutter/qr_flutter.dart';

import 'package:jam_ai_app/features/session/screens/session_qr_screen.dart';

void main() {
  Future<void> pumpQrScreen(
    WidgetTester tester, {
    String sessionCode = 'AB12CD',
    String qrPayload = 'jamai://join/AB12CD',
  }) async {
    final router = GoRouter(
      initialLocation: '/session/test-id/qr',
      routes: [
        GoRoute(
          path: '/session/:id/qr',
          builder: (c, s) => SessionQrScreen(
            sessionId: s.pathParameters['id']!,
            sessionCode: sessionCode,
            qrPayload: qrPayload,
          ),
        ),
        GoRoute(
          path: '/session/:id',
          builder: (c, s) => Scaffold(body: Text('SESSION_${s.pathParameters['id']}')),
        ),
        GoRoute(path: '/home', builder: (c, s) => const Scaffold(body: Text('HOME_PLACEHOLDER'))),
      ],
    );
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();
  }

  testWidgets('renders the real session code and a QrImageView when qr_payload is present',
      (tester) async {
    await pumpQrScreen(tester, sessionCode: 'AB12CD', qrPayload: 'jamai://join/AB12CD');

    expect(find.text('AB12CD'), findsOneWidget);
    expect(find.text('YOUR JAM IS LIVE'), findsOneWidget);
    // QrImageView's encoded data isn't publicly readable (qr_flutter keeps
    // it as a private field) — the source itself passes `qrPayload`
    // straight through with no transformation, so rendering it at all here
    // is the meaningful assertion; the "no invented format" guarantee comes
    // from reading session_qr_screen.dart's single `data: qrPayload` call.
    expect(find.byType(QrImageView), findsOneWidget);
  });

  testWidgets('tapping Start jamming navigates to the live session route', (tester) async {
    await pumpQrScreen(tester);

    await tester.tap(find.text('Start jamming'));
    await tester.pumpAndSettle();

    expect(find.text('SESSION_test-id'), findsOneWidget);
  });

  testWidgets('empty sessionCode/qrPayload falls back gracefully instead of crashing',
      (tester) async {
    await pumpQrScreen(tester, sessionCode: '', qrPayload: '');

    expect(find.byType(QrImageView), findsNothing);
    expect(find.byIcon(Icons.qr_code_2), findsOneWidget);
  });
}
