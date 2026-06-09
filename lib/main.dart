import 'package:flutter/material.dart';
import 'core/theme.dart';

void main() {
  runApp(const JamAiApp());
}

class JamAiApp extends StatelessWidget {
  const JamAiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'JAM AI',
      theme: jamAiTheme,
      debugShowCheckedModeBanner: false,
      home: const Scaffold(
        body: Center(
          child: Text('JAM AI is running ✓'),
        ),
      ),
    );
  }
}
