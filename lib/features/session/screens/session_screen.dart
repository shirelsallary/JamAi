import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';

class SessionScreen extends StatefulWidget {
  final String sessionId;

  const SessionScreen({super.key, required this.sessionId});

  @override
  State<SessionScreen> createState() => _SessionScreenState();
}

class _SessionScreenState extends State<SessionScreen> {
  List<Map<String, dynamic>> _tracks = [];
  bool _isLoading = true;
  String? _currentTrackId;
  WebSocketChannel? _channel;
  String? _sessionId;

  @override
  void initState() {
    super.initState();
    _sessionId = widget.sessionId;
    _loadQueue();
    _connectWebSocket();
  }

  @override
  void dispose() {
    _channel?.sink.close();
    super.dispose();
  }

  Future<void> _loadQueue() async {
    final token = await AuthService.getToken();
    if (!mounted) return;
    if (token == null) {
      context.go('/');
      return;
    }

    try {
      final response = await http.get(
        Uri.parse('$kBaseUrl/queue/$_sessionId'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (!mounted) return;

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as List<dynamic>;
        setState(() {
          _tracks = data.cast<Map<String, dynamic>>();
          _currentTrackId = _tracks.isNotEmpty
              ? _tracks.first['track_id'] as String?
              : null;
          _isLoading = false;
        });
      } else {
        setState(() => _isLoading = false);
      }
    } catch (_) {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _connectWebSocket() async {
    final token = await AuthService.getToken();
    if (!mounted) return;

    final wsUri = Uri.parse('$kWsUrl/ws/sessions/$_sessionId?token=$token');
    _channel = WebSocketChannel.connect(wsUri);
    _channel!.stream.listen(
      (message) {
        final data = jsonDecode(message as String);
        if (data['event'] == 'queue_updated') {
          _loadQueue();
        }
      },
      onError: (_) {},
      onDone: () {},
    );
  }

  Future<void> _skipTrack() async {
    final token = await AuthService.getToken();
    if (!mounted) return;
    if (token == null) return;

    try {
      await http.patch(
        Uri.parse('$kBaseUrl/queue/$_sessionId/skip'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({'playback_pct': 35.0}),
      );
    } catch (_) {}

    if (mounted) await _loadQueue();
  }

  Future<void> _endSession() async {
    final token = await AuthService.getToken();
    if (!mounted) return;

    if (token != null) {
      try {
        await http.post(
          Uri.parse('$kBaseUrl/sessions/$_sessionId/close'),
          headers: {'Authorization': 'Bearer $token'},
        );
      } catch (_) {}
    }

    if (mounted) context.go('/export/$_sessionId');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('JAM Session'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
          onPressed: () => context.go('/home'),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.exit_to_app, color: Colors.white),
            onPressed: _endSession,
            tooltip: 'End Session',
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator(color: kPrimary))
          : Column(
              children: [
                if (_tracks.isNotEmpty)
                  _NowPlayingCard(
                    key: ValueKey(_currentTrackId),
                    track: _tracks.first,
                    onSkip: _skipTrack,
                  ),
                Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Row(
                    children: [
                      const Text(
                        'Up Next',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      const Spacer(),
                      Text(
                        '${_tracks.length} tracks',
                        style: const TextStyle(
                            color: kTextSecondary, fontSize: 13),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: _tracks.length <= 1
                      ? const Center(
                          child: Text(
                            'Queue is empty',
                            style: TextStyle(color: kTextSecondary),
                          ),
                        )
                      : ListView.builder(
                          itemCount: _tracks.length - 1,
                          itemBuilder: (ctx, i) => _QueueTrackTile(
                            track: _tracks[i + 1],
                            position: i + 2,
                          ),
                        ),
                ),
              ],
            ),
      bottomNavigationBar: _tracks.isEmpty
          ? null
          : _PlayerControls(
              onSkip: _skipTrack,
              onEnd: _endSession,
            ),
    );
  }
}

// ---------------------------------------------------------------------------
// Now playing card
// ---------------------------------------------------------------------------

class _NowPlayingCard extends StatelessWidget {
  final Map<String, dynamic> track;
  final VoidCallback onSkip;

  const _NowPlayingCard({
    super.key,
    required this.track,
    required this.onSkip,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: kCardAccent,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'NOW PLAYING',
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.bold,
                color: kPrimary,
                letterSpacing: 1.5,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              track['title'] as String? ?? '',
              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            Text(
              track['artist'] as String? ?? '',
              style: const TextStyle(color: kTextSecondary),
            ),
            const SizedBox(height: 16),
            const LinearProgressIndicator(
              value: 0.35,
              backgroundColor: kSurface,
              valueColor: AlwaysStoppedAnimation(kPrimary),
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'Platform: ${track['platform']}',
                  style: const TextStyle(fontSize: 12, color: kTextSecondary),
                ),
                Text(
                  'Score: ${((track['weight_score'] as num) * 100).toStringAsFixed(0)}%',
                  style: const TextStyle(fontSize: 12, color: kPrimary),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Queue track tile
// ---------------------------------------------------------------------------

class _QueueTrackTile extends StatelessWidget {
  final Map<String, dynamic> track;
  final int position;

  const _QueueTrackTile({required this.track, required this.position});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: kCardAccent,
        child: Text(
          '$position',
          style: const TextStyle(color: kPrimary, fontSize: 12),
        ),
      ),
      title: Text(
        track['title'] as String? ?? '',
        style: const TextStyle(fontWeight: FontWeight.bold),
      ),
      subtitle: Text(track['artist'] as String? ?? ''),
      trailing: Text(
        _formatDuration(track['duration_ms'] as int? ?? 0),
        style: const TextStyle(color: kTextSecondary, fontSize: 12),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Player controls
// ---------------------------------------------------------------------------

class _PlayerControls extends StatelessWidget {
  final VoidCallback onSkip;
  final VoidCallback onEnd;

  const _PlayerControls({required this.onSkip, required this.onEnd});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withAlpha(20),
            blurRadius: 8,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              ElevatedButton.icon(
                icon: const Icon(Icons.skip_next),
                label: const Text('Skip'),
                style: ElevatedButton.styleFrom(backgroundColor: kRed),
                onPressed: onSkip,
              ),
              OutlinedButton.icon(
                icon: const Icon(Icons.stop_circle_outlined),
                label: const Text('End JAM'),
                style: OutlinedButton.styleFrom(foregroundColor: kRed),
                onPressed: onEnd,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

String _formatDuration(int ms) {
  final minutes = (ms / 60000).floor();
  final seconds = ((ms % 60000) / 1000).floor();
  return '$minutes:${seconds.toString().padLeft(2, '0')}';
}
