import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class ExportScreen extends StatelessWidget {
  final String sessionId;

  const ExportScreen({super.key, required this.sessionId});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Export'),
          leading: Navigator.canPop(context)
              ? IconButton(
                  icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
                  onPressed: () => context.pop(),
                )
              : null,
        ),
        body: Center(child: Text('Export Screen — ID: $sessionId')),
      );
}
