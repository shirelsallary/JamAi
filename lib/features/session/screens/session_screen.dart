import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';
import '../../../core/youtube_player_event.dart';
import '../widgets/youtube_player_widget.dart';

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
  // Section 7 — transparency: distinguish "still building" / "found fewer
  // matches than requested" / "found nothing" from a silent empty screen.
  String _queueBuildStatus = 'empty';
  double? _effectiveThreshold;

  // Real playback control — host_platform decides which path applies
  // (Spotify device control vs. YouTube IFrame Player); it has no reliable
  // source other than this response (not in route params, not returned to
  // guests at join time, no GET /sessions/{id} endpoint exists).
  String? _hostPlatform;
  // 'playing' | 'no_active_device' | 'error' | null (not yet known/attempted)
  String? _spotifyPlaybackStatus;
  bool _isRetryingPlayback = false;
  bool _attemptedInitialSpotifyPlayback = false;

  // Guards against firing a second auto-skip for the same track while the
  // first one's backend call + queue reload is still in flight (e.g. the
  // IFrame Player can fire more than one 'ended'/'error' event in a row).
  bool _autoAdvancePending = false;

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
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final tracks = (data['tracks'] as List<dynamic>).cast<Map<String, dynamic>>();
        setState(() {
          _tracks = tracks;
          _queueBuildStatus = data['queue_build_status'] as String? ?? 'empty';
          _effectiveThreshold = (data['effective_threshold'] as num?)?.toDouble();
          _hostPlatform = data['host_platform'] as String?;
          final newCurrentTrackId = _tracks.isNotEmpty
              ? _tracks.first['track_id'] as String?
              : null;
          if (newCurrentTrackId != _currentTrackId) {
            _autoAdvancePending = false;
          }
          _currentTrackId = newCurrentTrackId;
          _isLoading = false;
        });

        // One-time on-mount attempt — covers a client that opens the session
        // AFTER the backend's own auto-attempt (queue_optimizer.py, at initial
        // build/skip time) already fired and broadcast a playback_status that
        // this client wasn't connected to the WebSocket to receive; WS
        // messages aren't persisted/replayed. Live updates while the screen
        // stays open come from the WebSocket listener below instead.
        if (!_attemptedInitialSpotifyPlayback &&
            _hostPlatform == 'spotify' &&
            _tracks.isNotEmpty) {
          _attemptedInitialSpotifyPlayback = true;
          _attemptSpotifyPlayback();
        }
      } else {
        setState(() => _isLoading = false);
      }
    } catch (_) {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  Future<void> _attemptSpotifyPlayback() async {
    final token = await AuthService.getToken();
    if (!mounted || token == null) return;

    setState(() => _isRetryingPlayback = true);
    try {
      final response = await http.post(
        Uri.parse('$kBaseUrl/queue/$_sessionId/play'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (!mounted) return;
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        _handlePlaybackStatus(data);
      } else {
        setState(() => _spotifyPlaybackStatus = 'error');
      }
    } catch (_) {
      if (mounted) setState(() => _spotifyPlaybackStatus = 'error');
    } finally {
      if (mounted) setState(() => _isRetryingPlayback = false);
    }
  }

  void _handlePlaybackStatus(Map<String, dynamic> status) {
    if (!mounted) return;
    setState(() => _spotifyPlaybackStatus = status['status'] as String?);
  }

  Future<void> _connectWebSocket() async {
    final token = await AuthService.getToken();
    if (!mounted) return;

    final wsUri = Uri.parse('$kWsUrl/ws/sessions/$_sessionId?token=$token');
    try {
      _channel = WebSocketChannel.connect(wsUri);
      // WebSocketChannel.connect() returns immediately, without waiting for
      // the handshake — a failed connection surfaces through this Future,
      // not through the stream's onError below (which is for errors AFTER a
      // successful connection). Without awaiting `ready` here, a failed
      // handshake becomes an unhandled zone error that bypasses this
      // try/catch entirely (it rejects a Future nothing is awaiting).
      await _channel!.ready;
      _channel!.stream.listen(
        (message) {
          final data = jsonDecode(message as String);
          if (data['event'] == 'queue_updated') {
            _loadQueue();
            final playbackStatus = data['playback_status'] as Map<String, dynamic>?;
            if (playbackStatus != null) {
              _handlePlaybackStatus(playbackStatus);
            }
          }
        },
        onError: (_) {},
        onDone: () {},
      );
    } catch (_) {
      // The handshake itself (not just the eventual stream) can fail — e.g.
      // the backend is unreachable or rejects the upgrade. Live queue/
      // playback updates just won't arrive; _loadQueue()'s own polling-free
      // initial fetch and the on-mount Spotify attempt already happened
      // independently of this connection.
    }
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

  void _handleYouTubePlayerEvent(YouTubePlayerEvent event) {
    switch (event.type) {
      case YouTubePlayerEventType.stateChange:
        if (event.state == YouTubePlayerState.ended) {
          _autoAdvance();
        }
        break;
      case YouTubePlayerEventType.error:
        // Content-coverage gap (not every matched track necessarily has a
        // working embeddable video ID) — skip past it automatically rather
        // than stalling the whole session on one bad track, and tell the
        // host plainly rather than failing silently.
        _autoAdvance();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Skipped 1 track — unavailable for playback'),
              backgroundColor: kTextSecondary,
              duration: Duration(seconds: 3),
            ),
          );
        }
        break;
      case YouTubePlayerEventType.ready:
      case YouTubePlayerEventType.unknown:
        break;
    }
  }

  Future<void> _autoAdvance() async {
    if (_autoAdvancePending) return;
    _autoAdvancePending = true;
    await _skipTrack();
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
                if (_queueBuildStatus == 'partial' || _queueBuildStatus == 'empty')
                  _QueueStatusBanner(
                    status: _queueBuildStatus,
                    effectiveThreshold: _effectiveThreshold,
                  ),
                if (_hostPlatform == 'spotify' &&
                    (_spotifyPlaybackStatus == 'no_active_device' ||
                        _spotifyPlaybackStatus == 'error'))
                  _SpotifyPlaybackBanner(
                    key: const Key('spotify-playback-banner'),
                    status: _spotifyPlaybackStatus!,
                    isRetrying: _isRetryingPlayback,
                    onRetry: _attemptSpotifyPlayback,
                  ),
                if (_tracks.isNotEmpty)
                  _NowPlayingCard(
                    key: ValueKey(_currentTrackId),
                    track: _tracks.first,
                    onSkip: _skipTrack,
                    hostPlatform: _hostPlatform,
                    onYouTubeEvent: _handleYouTubePlayerEvent,
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
// Spotify real-playback banner — the device-must-be-active constraint is a
// routine, expected condition (Spotify's Web API can't wake a device from
// cold), not a rare failure, so this must read as a clear instruction with
// an easy retry, never a generic/alarming error.
// ---------------------------------------------------------------------------

class _SpotifyPlaybackBanner extends StatelessWidget {
  final String status; // 'no_active_device' | 'error'
  final bool isRetrying;
  final VoidCallback onRetry;

  const _SpotifyPlaybackBanner({
    super.key,
    required this.status,
    required this.isRetrying,
    required this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    final message = status == 'no_active_device'
        ? 'Open Spotify on your phone and play (or pause) any track, then retry.'
        : "Couldn't start playback on Spotify. Check your connection and retry.";
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: kRed.withAlpha(20),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: kRed.withAlpha(80)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.music_off, size: 18, color: kRed),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message, style: const TextStyle(fontSize: 12.5, color: kTextSecondary)),
          ),
          const SizedBox(width: 8),
          isRetrying
              ? const SizedBox(
                  height: 18,
                  width: 18,
                  child: CircularProgressIndicator(strokeWidth: 2, color: kRed),
                )
              : TextButton(
                  key: const Key('retry-playback-button'),
                  onPressed: onRetry,
                  child: const Text('Retry'),
                ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Queue status banner (Section 7) — replaces a silent empty screen with a
// concrete explanation of why the queue is short/empty.
// ---------------------------------------------------------------------------

class _QueueStatusBanner extends StatelessWidget {
  final String status;
  final double? effectiveThreshold;

  const _QueueStatusBanner({required this.status, required this.effectiveThreshold});

  @override
  Widget build(BuildContext context) {
    final pct = effectiveThreshold != null ? (effectiveThreshold! * 100).round() : null;
    final message = status == 'empty'
        ? "We couldn't find any matching songs yet in the connected playlists. "
            'The queue will update automatically once it does.'
        : pct != null
            ? 'We found expanded matches ($pct%) because there aren\'t enough '
                'songs in the connected playlists yet.'
            : "We found fewer matches than usual — the queue will keep updating.";
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 12, 16, 0),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: kPrimary.withAlpha(20),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: kPrimary.withAlpha(80)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline, size: 18, color: kPrimary),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message, style: const TextStyle(fontSize: 12.5, color: kTextSecondary)),
          ),
        ],
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
  final String? hostPlatform;
  final ValueChanged<YouTubePlayerEvent>? onYouTubeEvent;

  const _NowPlayingCard({
    super.key,
    required this.track,
    required this.onSkip,
    this.hostPlatform,
    this.onYouTubeEvent,
  });

  @override
  Widget build(BuildContext context) {
    final isYouTube = hostPlatform == 'youtube' && onYouTubeEvent != null;
    final videoId = track['track_id'] as String?;

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
            if (isYouTube && videoId != null && videoId.isNotEmpty) ...[
              // Real YouTube playback — a persistent, visibly-sized IFrame
              // Player (see YouTubePlayerWidget's own doc comment on the
              // IFrame API's on-screen-visibility requirement for autoplay).
              ClipRRect(
                borderRadius: BorderRadius.circular(10),
                child: SizedBox(
                  key: const Key('youtube-player-container'),
                  height: 200,
                  child: YouTubePlayerWidget(
                    key: ValueKey('yt-player-$videoId'),
                    videoId: videoId,
                    onEvent: onYouTubeEvent!,
                  ),
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Keep JAM AI open to keep the music playing.',
                style: TextStyle(fontSize: 11, color: kTextSecondary, fontStyle: FontStyle.italic),
              ),
            ] else
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
