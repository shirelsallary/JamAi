import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';

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
      appBar: AppBar(
        title: const Text('Session Export'),
        automaticallyImplyLeading: false,
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (_isExporting) ...[
                const CircularProgressIndicator(color: kPrimary),
                const SizedBox(height: 24),
                const Text(
                  'Saving your JAM playlist...',
                  style: TextStyle(color: kTextSecondary),
                ),
              ] else if (_error != null) ...[
                const Icon(Icons.error_outline, size: 64, color: kRed),
                const SizedBox(height: 16),
                Text(
                  _error!,
                  style: const TextStyle(color: kRed),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 24),
                ElevatedButton(
                  onPressed: _exportSession,
                  child: const Text('Try Again'),
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: () => context.go('/home'),
                  child: const Text('Go to Home'),
                ),
              ] else if (_exported) ...[
                const Icon(Icons.check_circle, size: 80, color: kGreen),
                const SizedBox(height: 16),
                const Text(
                  'JAM Saved! 🎵',
                  style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.bold,
                    color: kTextPrimary,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '$_trackCount tracks saved to your playlist',
                  style:
                      const TextStyle(color: kTextSecondary, fontSize: 16),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 32),
                if (_playlistUrl != null)
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: kCardAccent,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: kPrimary.withAlpha(50)),
                    ),
                    child: Column(
                      children: [
                        const Text(
                          'Your Playlist',
                          style: TextStyle(
                              fontWeight: FontWeight.bold, color: kPrimary),
                        ),
                        const SizedBox(height: 8),
                        SelectableText(
                          _playlistUrl!,
                          style: const TextStyle(
                              fontSize: 12, color: kTextSecondary),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 12),
                        ElevatedButton.icon(
                          icon: const Icon(Icons.open_in_new),
                          label: const Text('Open Playlist'),
                          style: ElevatedButton.styleFrom(
                              backgroundColor: kGreen),
                          onPressed: _openPlaylist,
                        ),
                      ],
                    ),
                  ),
                const SizedBox(height: 24),
                ElevatedButton.icon(
                  icon: const Icon(Icons.home),
                  label: const Text('Back to Home'),
                  onPressed: () => context.go('/home'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
