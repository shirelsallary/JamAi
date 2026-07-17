// Default Flutter-template smoke test, updated to match the real app — it
// previously checked for placeholder text ('JAM AI is running ✓') that
// hasn't existed since the app grew past its initial scaffold, so it was
// failing independent of and before the Bug 1/Bug 2 fixes in this change.

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:jam_ai_app/main.dart';

void main() {
  testWidgets('App boots to the splash screen', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});

    await tester.pumpWidget(const JamAiApp());
    await tester.pump();

    expect(find.text('JAM AI'), findsOneWidget);
    expect(find.text('Shared listening, reimagined'), findsOneWidget);

    // SplashScreen schedules a Future.delayed(2s) redirect — let it fire and
    // settle so no pending Timer remains when the test tears down.
    await tester.pump(const Duration(seconds: 3));
  });
}
