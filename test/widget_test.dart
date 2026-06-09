import 'package:flutter_test/flutter_test.dart';
import 'package:jam_ai_app/main.dart';

void main() {
  testWidgets('App renders startup text', (WidgetTester tester) async {
    await tester.pumpWidget(const JamAiApp());
    expect(find.text('JAM AI is running ✓'), findsOneWidget);
  });
}
