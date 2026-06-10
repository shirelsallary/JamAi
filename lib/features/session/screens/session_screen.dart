import 'package:flutter/material.dart';

class SessionScreen extends StatelessWidget {
  final String sessionId;

  const SessionScreen({super.key, required this.sessionId});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Session')),
        body: Center(child: Text('Session Screen — ID: $sessionId')),
      );
}
