import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';

class ConnectPlatformScreen extends StatefulWidget {
  const ConnectPlatformScreen({super.key});

  @override
  State<ConnectPlatformScreen> createState() => _ConnectPlatformScreenState();
}

class _ConnectPlatformScreenState extends State<ConnectPlatformScreen> {
  bool _isConnecting = false;
  bool _showVerifyButton = false;
  String? _error;

  Future<void> _connectPlatform(String platform) async {
    setState(() {
      _isConnecting = true;
      _error = null;
    });

    try {
      final url = Uri.parse('$kBaseUrl/auth/oauth/$platform');
      if (await canLaunchUrl(url)) {
        await launchUrl(url, mode: LaunchMode.externalApplication);
        if (!mounted) return;
        setState(() => _showVerifyButton = true);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
                'Follow the steps in your browser, then come back here'),
            duration: Duration(seconds: 5),
          ),
        );
      } else {
        setState(() => _error = 'Could not open browser. Try again.');
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'Connection failed. Please try again.');
    } finally {
      if (mounted) setState(() => _isConnecting = false);
    }
  }

  Future<void> _verifyAndContinue() async {
    setState(() {
      _isConnecting = true;
      _error = null;
    });

    try {
      final token = await AuthService.getToken();
      if (token == null) {
        if (mounted) context.go('/');
        return;
      }
      final me = await AuthService.getMe(token);
      if (!mounted) return;

      final platformToken = me?['platform_token'];
      if (platformToken != null && platformToken.toString().isNotEmpty) {
        context.go('/home');
      } else {
        setState(() => _error = 'Platform not connected yet. Try again.');
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'Connection failed. Please try again.');
    } finally {
      if (mounted) setState(() => _isConnecting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBackground,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(Icons.music_note, size: 64, color: kPrimary),
              const SizedBox(height: 16),
              const Text(
                'Connect your music',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  color: kTextPrimary,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Choose the platform you use to listen to music',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 14, color: kTextSecondary),
              ),
              const SizedBox(height: 48),
              _PlatformConnectButton(
                label: 'Connect Spotify',
                color: kGreen,
                onTap: _isConnecting ? null : () => _connectPlatform('spotify'),
              ),
              const SizedBox(height: 16),
              _PlatformConnectButton(
                label: 'Connect YouTube Music',
                color: kRed,
                onTap: _isConnecting ? null : () => _connectPlatform('youtube'),
              ),
              const SizedBox(height: 24),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    _error!,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: kRed, fontSize: 12),
                  ),
                ),
              if (_showVerifyButton)
                ElevatedButton(
                  onPressed: _isConnecting ? null : _verifyAndContinue,
                  child: _isConnecting
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text('I connected my account'),
                ),
              TextButton(
                onPressed: () => context.go('/home'),
                child: const Text('Skip for now'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Platform connect button
// ---------------------------------------------------------------------------

class _PlatformConnectButton extends StatelessWidget {
  final String label;
  final Color color;
  final VoidCallback? onTap;

  const _PlatformConnectButton({
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Opacity(
        opacity: onTap == null ? 0.5 : 1.0,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: color.withAlpha(20),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color, width: 1.5),
          ),
          child: Row(
            children: [
              Container(
                width: 16,
                height: 16,
                decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              ),
              const SizedBox(width: 8),
              Text(
                label,
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
              const Spacer(),
              Icon(Icons.arrow_forward_ios, size: 16, color: color),
            ],
          ),
        ),
      ),
    );
  }
}
