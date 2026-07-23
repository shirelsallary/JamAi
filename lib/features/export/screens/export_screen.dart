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
  String? _launchError;

  static const _kLaunchErrorMessage =
      "Couldn't open the playlist - try again or check your browser";

  @override
  void initState() {
    super.initState();
    _sessionId = widget.sessionId;
    // Reached unconditionally whenever the host ends the session — this
    // screen itself always shows "Playback ended" with an Export button and
    // a Back to Home button, regardless of whether export ends up
    // succeeding. Export only runs when the host explicitly taps Export
    // Playlist below, not automatically on load.
  }

  Future<void> _exportSession() async {
    setState(() => _isExporting = true);

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
        _showExportFailedSnackBar();
      }
    } catch (_) {
      _showExportFailedSnackBar();
    }
  }

  // No separate error screen and no navigating away — stay right here on
  // "Playback ended" with Export Playlist still up to retry, and a light,
  // non-blocking SnackBar instead. Deliberately doesn't surface the actual
  // status code/exception (e.g. the known YouTube 401 on create_playlist) —
  // that's a separate, already-tracked issue, not something to explain here.
  void _showExportFailedSnackBar() {
    if (!mounted) return;
    setState(() => _isExporting = false);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text("Couldn't export right now — you can try again."),
        backgroundColor: kTextSecondary,
        duration: Duration(seconds: 4),
      ),
    );
  }

  Future<void> _openPlaylist() async {
    final url = _playlistUrl;
    if (url == null) {
      setState(() {
        _launchError = _kLaunchErrorMessage;
      });
      return;
    }

    try {
      bool launched;
      if (Platform.isLinux) {
        final result = await Process.run('xdg-open', [url]);
        launched = result.exitCode == 0;
      } else {
        launched = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
      }
      if (!mounted) return;
      setState(() {
        _launchError = launched ? null : _kLaunchErrorMessage;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _launchError = _kLaunchErrorMessage;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Session Export'),
        // No visible back button on any state here — "Back to Home" below
        // is the one, always-available way out at every stage.
        automaticallyImplyLeading: false,
      ),
      body: GradientBackground(
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(kSpaceLg),
              child: _isExporting
                  ? _buildLoadingState()
                  : _exported
                      ? _buildSuccessState()
                      : _buildEndedState(),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildEndedState() {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.stop_circle_outlined, size: 80, color: kPrimary),
        const SizedBox(height: kSpaceMd),
        Text('Playback ended', style: kDuskTextTheme.headlineMedium),
        const SizedBox(height: kSpaceSm),
        Text(
          'Save this session\'s queue as a playlist to keep it.',
          style: kDuskTextTheme.bodyMedium,
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: kSpaceXl),
        PrimaryButton(
          label: 'Export Playlist',
          icon: Icons.save_alt,
          onPressed: _exportSession,
        ),
        const SizedBox(height: kSpaceLg),
        TextButton(
          onPressed: () => context.go('/home'),
          child: const Text('Back to Home'),
        ),
      ],
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
          // Spotify" — the playlist is already saved (the Export Playlist
          // tap that got us here), so this button opens/confirms it rather
          // than saving anything new. Also, export targets whichever
          // platform the host connected (Spotify or YouTube — see
          // playlist_service.py's get_platform_adapter), so a Spotify-
          // specific label would be inaccurate for YouTube hosts.
          PrimaryButton(
            label: 'Open Playlist',
            icon: Icons.open_in_new,
            onPressed: _openPlaylist,
          ),
          if (_launchError != null) ...[
            const SizedBox(height: kSpaceMd),
            AppBanner(message: _launchError!, variant: AppBannerVariant.error),
          ],
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
