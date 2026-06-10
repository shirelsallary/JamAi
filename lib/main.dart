import 'package:flutter/material.dart';
import 'core/theme.dart';
import 'core/router.dart';

void main() {
  runApp(const JamAiApp());
}

class JamAiApp extends StatelessWidget {
  const JamAiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'JAM AI',
      theme: jamAiTheme,
      debugShowCheckedModeBanner: false,
      routerConfig: appRouter,
    );
  }
}
