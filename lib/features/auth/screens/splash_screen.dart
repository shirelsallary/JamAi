import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/auth_service.dart';
import '../../../core/theme.dart';

class SplashScreen extends StatefulWidget {
  const SplashScreen({super.key});

  @override
  State<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends State<SplashScreen> {
  @override
  void initState() {
    super.initState();
    Future.delayed(const Duration(seconds: 2), () async {
      if (!mounted) return;
      final token = await AuthService.getToken();
      if (!mounted) return;

      if (token == null) {
        context.go('/');
        return;
      }

      final user = await AuthService.getMe(token);
      if (!mounted) return;

      final platformToken = user?['platform_token'];
      final hasPlatform =
          platformToken != null && platformToken.toString().isNotEmpty;
      context.go(hasPlatform ? '/home' : '/connect-platform');
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kPrimary,
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.music_note, size: 80, color: Colors.white),
            const SizedBox(height: 16),
            const Text(
              'JAM AI',
              style: TextStyle(
                fontSize: 36,
                fontWeight: FontWeight.bold,
                color: Colors.white,
                letterSpacing: 4,
              ),
            ),
            const SizedBox(height: 8),
            const Text(
              'Shared listening, reimagined',
              style: TextStyle(color: Colors.white70, fontSize: 14),
            ),
            const SizedBox(height: 48),
            const CircularProgressIndicator(color: Colors.white70),
          ],
        ),
      ),
    );
  }
}
