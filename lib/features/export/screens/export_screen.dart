import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

class ExportScreen extends StatefulWidget {
  final String sessionId;

  const ExportScreen({super.key, required this.sessionId});

  @override
  State<ExportScreen> createState() => _ExportScreenState();
}

class _ExportScreenState extends State<ExportScreen> {
  String? _sessionId;
  bool _isExporting = false;
  bool _exported = false;
  String? _playlistUrl;
  int? _trackCount;
  String? _error;

  @override
  void initState() {
    super.initState();
    _sessionId = widget.sessionId;
    _exportSession();
  }

  Future<void> _exportSession() async {
    setState(() {
      _isExporting = true;
      _error = null;
    });

    try {
      final token = await AuthService.getToken();
      if (!mounted) return;
      if (token == null) {
        context.go('/');
        return;
      }

      final response = await http.post(
        Uri.parse('$kBaseUrl/sessions/$_sessionId/export'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (!mounted) return;

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        setState(() {
          _isExporting = false;
          _exported = true;
          _playlistUrl = data['playlist_url'] as String?;
          _trackCount = data['track_count'] as int?;
        });
      } else {
        setState(() {
          _isExporting = false;
          _error = 'Export failed. Session may already be exported.';
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _isExporting = false;
          _error = 'Export failed. Session may already be exported.';
        });
      }
    }
  }

  Future<void> _openPlaylist() async {
    final url = _playlistUrl;
    if (url == null) return;

    if (Platform.isLinux) {
      await Process.run('xdg-open', [url]);
    } else {
      await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Session Export'),
        // Terminal screen — reached only after a session ends, with no
        // meaningful "back" destination (Navigator.canPop is false here,
        // same rationale as SessionQrScreen). Preserved unchanged.
        automaticallyImplyLeading: false,
      ),
      body: GradientBackground(
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(kSpaceLg),
              child: _isExporting
                  ? _buildLoadingState()
                  : _error != null
                      ? _buildErrorState()
                      : _exported
                          ? _buildSuccessState()
                          : const SizedBox.shrink(),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildLoadingState() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const CircularProgressIndicator(color: kPrimary),
        const SizedBox(height: kSpaceLg),
        Text(
          'Saving your JAM playlist...',
          style: kDuskTextTheme.bodyMedium,
        ),
      ],
    );
  }

  Widget _buildErrorState() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.error_outline, size: 64, color: kRed),
        const SizedBox(height: kSpaceMd),
        AppBanner(message: _error!, variant: AppBannerVariant.error),
        const SizedBox(height: kSpaceLg),
        PrimaryButton(label: 'Try Again', onPressed: _exportSession),
        const SizedBox(height: kSpaceSm),
        TextButton(
          onPressed: () => context.go('/home'),
          child: const Text('Go to Home'),
        ),
      ],
    );
  }

  Widget _buildSuccessState() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.check_circle, size: 80, color: kGreen),
        const SizedBox(height: kSpaceMd),
        Text('JAM Saved! \u{1F3B5}', style: kDuskTextTheme.headlineMedium),
        const SizedBox(height: kSpaceSm),
        Text(
          '$_trackCount tracks saved to your playlist',
          style: kDuskTextTheme.bodyMedium,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: kSpaceXl),
        if (_playlistUrl != null) ...[
          Container(
            padding: const EdgeInsets.all(kSpaceMd),
            decoration: BoxDecoration(
              color: kCardAccent,
              borderRadius: BorderRadius.circular(kRadiusLg),
              border: Border.all(color: kPrimary.withAlpha(kAlphaSoft)),
            ),
            child: Column(
              children: [
                Text('Your Playlist', style: kDuskTextTheme.titleMedium?.copyWith(color: kPrimary)),
                const SizedBox(height: kSpaceSm),
                SelectableText(
                  _playlistUrl!,
                  style: kDuskTextTheme.bodySmall,
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
          const SizedBox(height: kSpaceLg),
          // Labeled "Open Playlist" rather than the mockup's "Save to
          // Spotify" — the playlist is already saved automatically (export
          // runs on screen load, above), so this button opens/confirms it
          // rather than saving anything new. Also, export targets whichever
          // platform the host connected (Spotify or YouTube — see
          // playlist_service.py's get_platform_adapter), so a Spotify-
          // specific label would be inaccurate for YouTube hosts.
          PrimaryButton(
            label: 'Open Playlist',
            icon: Icons.open_in_new,
            onPressed: _openPlaylist,
          ),
        ],
        const SizedBox(height: kSpaceLg),
        TextButton(
          onPressed: () => context.go('/home'),
          child: const Text('Back to Home'),
        ),
      ],
    );
  }
}
