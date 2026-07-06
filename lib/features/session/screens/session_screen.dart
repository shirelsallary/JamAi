import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class SessionScreen extends StatelessWidget {
  final String sessionId;

  const SessionScreen({super.key, required this.sessionId});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Session'),
          leading: Navigator.canPop(context)
              ? IconButton(
                  icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
                  onPressed: () => context.pop(),
                )
              : null,
        ),
        body: Center(child: Text('Session Screen — ID: $sessionId')),
      );
}
