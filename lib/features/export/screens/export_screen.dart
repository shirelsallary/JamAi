import 'package:flutter/material.dart';

class ExportScreen extends StatelessWidget {
  final String sessionId;

  const ExportScreen({super.key, required this.sessionId});

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Export')),
        body: Center(child: Text('Export Screen — ID: $sessionId')),
      );
}
