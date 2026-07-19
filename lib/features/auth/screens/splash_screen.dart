import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../core/auth_service.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

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
      body: GradientBackground(
        child: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.music_note, size: 80, color: kPrimary),
              const SizedBox(height: kSpaceMd),
              Text('JAM AI', style: kDuskTextTheme.displayLarge),
              const SizedBox(height: kSpaceSm),
              const Text(
                'Shared listening, reimagined',
                style: TextStyle(color: kTextSecondary, fontSize: 14),
              ),
              const SizedBox(height: kSpaceXxl),
              const CircularProgressIndicator(color: kPrimary),
            ],
          ),
        ),
      ),
    );
  }
}
