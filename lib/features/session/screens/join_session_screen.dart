import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';

class JoinSessionScreen extends StatefulWidget {
  // Populated when this screen is reached via a jamai://join/{code} deep
  // link (QR code scan or shared link) — see main.dart's deep-link listener.
  final String? initialCode;

  const JoinSessionScreen({super.key, this.initialCode});

  @override
  State<JoinSessionScreen> createState() => _JoinSessionScreenState();
}

class _JoinSessionScreenState extends State<JoinSessionScreen> {
  late final TextEditingController _codeController;
  String _code = '';
  bool _isLoading = false;
  String? _error;

  // Section 0 — the guest's own connected platform, independent of the
  // host's. Auto-selected (at most one connected platform per account today).
  bool _loadingPlatform = true;
  String? _selectedPlatform;

  @override
  void initState() {
    super.initState();
    final prefill = widget.initialCode?.toUpperCase() ?? '';
    _code = prefill;
    _codeController = TextEditingController(text: prefill);
    _loadSelectedPlatform();
  }

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _loadSelectedPlatform() async {
    final token = await AuthService.getToken();
    if (!mounted) return;
    if (token == null) {
      context.go('/');
      return;
    }
    final me = await AuthService.getMe(token);
    if (!mounted) return;
    final platform = me?['platform'] as String?;
    final platformToken = me?['platform_token'] as String?;
    setState(() {
      _selectedPlatform =
          (platform != null && platformToken != null && platformToken.isNotEmpty)
              ? platform
              : null;
      _loadingPlatform = false;
    });
  }

  Future<void> _joinSession() async {
    if (_selectedPlatform == null) return;
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final token = await AuthService.getToken();
      if (!mounted) return;
      if (token == null) {
        context.go('/');
        return;
      }

      final response = await http.get(
        Uri.parse('$kBaseUrl/sessions/$_code/join?selected_platform=$_selectedPlatform'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (!mounted) return;

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        context.go('/session/${data['session_id']}');
      } else if (response.statusCode == 409) {
        setState(() => _error = 'You are already in this session');
      } else if (response.statusCode == 404) {
        setState(() =>
            _error = 'Session not found. Check the code and try again.');
      } else {
        setState(() => _error = 'Could not join session. Please try again.');
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Could not join session. Please try again.');
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Join JAM'),
        leading: Navigator.canPop(context)
            ? IconButton(
                icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
                onPressed: () => context.pop(),
              )
            : null,
      ),
      body: _loadingPlatform
          ? const Center(child: CircularProgressIndicator(color: kPrimary))
          : Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.people, size: 64, color: kPrimary),
                  const SizedBox(height: 16),
                  const Text(
                    'Enter Session Code',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: kTextPrimary,
                    ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Ask the host for the 6-character code',
                    style: TextStyle(fontSize: 14, color: kTextSecondary),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 32),
                  TextField(
                    controller: _codeController,
                    maxLength: 6,
                    textAlign: TextAlign.center,
                    textCapitalization: TextCapitalization.characters,
                    style: const TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 8,
                    ),
                    decoration: const InputDecoration(
                      hintText: 'XXXXXX',
                      counterText: '',
                    ),
                    onChanged: (val) => setState(() => _code = val.toUpperCase()),
                  ),
                  const SizedBox(height: 16),
                  if (_selectedPlatform != null)
                    _PlatformBadge(platform: _selectedPlatform!)
                  else
                    _NoPlatformConnectedBanner(
                      onConnect: () => context.push('/connect-platform'),
                    ),
                  const SizedBox(height: 24),
                  if (_error != null)
                    Text(
                      _error!,
                      style: const TextStyle(color: kRed, fontSize: 13),
                    ),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: _code.length == 6 && !_isLoading && _selectedPlatform != null
                        ? _joinSession
                        : null,
                    child: _isLoading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Text('Join Session'),
                  ),
                ],
              ),
            ),
    );
  }
}

// ---------------------------------------------------------------------------
// Platform badge / no-platform banner (same visual language as CreateSessionScreen)
// ---------------------------------------------------------------------------

class _PlatformBadge extends StatelessWidget {
  final String platform;

  const _PlatformBadge({required this.platform});

  @override
  Widget build(BuildContext context) {
    final isSpotify = platform == 'spotify';
    final color = isSpotify ? kGreen : kRed;
    final label = isSpotify ? 'Joining via Spotify' : 'Joining via YouTube Music';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: color.withAlpha(20),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color, width: 1.5),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Text(label, style: TextStyle(fontWeight: FontWeight.w600, color: color, fontSize: 13)),
        ],
      ),
    );
  }
}

class _NoPlatformConnectedBanner extends StatelessWidget {
  final VoidCallback onConnect;

  const _NoPlatformConnectedBanner({required this.onConnect});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: kRed.withAlpha(20),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: kRed, width: 1.5),
      ),
      child: Column(
        children: [
          const Text(
            "You haven't connected a platform yet.",
            style: TextStyle(color: kRed, fontWeight: FontWeight.bold),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: onConnect,
            child: const Text('Connect Spotify or YouTube Music'),
          ),
        ],
      ),
    );
  }
}
