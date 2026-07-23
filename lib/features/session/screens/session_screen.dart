import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';
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

  // The backend has no distinct "still building" queue_build_status — a
  // freshly-created session that's still building and a session that
  // finished building with genuinely zero matches both report "empty"
  // (models.py only allows 'full'/'partial'/'empty'), and there's no
  // separate 'pending' status to tell them apart (a known backend
  // limitation, out of scope here). Deliberately biased toward "still
  // building": as long as the queue is empty and status is 'empty', always
  // show the loading state rather than risk mislabeling an in-progress
  // build as "nothing found". Accepted tradeoff: a session that genuinely
  // has zero matches never gets a distinct "nothing found" message and
  // instead stays on the loading state indefinitely — intentional, not a
  // bug to fix here.
  bool get _stillBuildingQueue => _tracks.isEmpty && _queueBuildStatus == 'empty';

  // Real playback control — host_platform decides which path applies
  // (Spotify device control vs. YouTube IFrame Player); it has no reliable
  // source other than this response (not in route params, not returned to
  // guests at join time, no GET /sessions/{id} endpoint exists).
  String? _hostPlatform;
  // 'playing' | 'no_active_device' | 'error' | null (not yet known/attempted)
  String? _spotifyPlaybackStatus;
  // Only meaningful when _spotifyPlaybackStatus == 'error' — e.g.
  // 'SPOTIFY_REAUTH_REQUIRED', which needs a "reconnect" action rather than
  // a plain "Retry" (retrying with the same dead token just fails again).
  String? _spotifyPlaybackReason;
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
        setState(() {
          _spotifyPlaybackStatus = 'error';
          _spotifyPlaybackReason = null;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _spotifyPlaybackStatus = 'error';
          _spotifyPlaybackReason = null;
        });
      }
    } finally {
      if (mounted) setState(() => _isRetryingPlayback = false);
    }
  }

  void _handlePlaybackStatus(Map<String, dynamic> status) {
    if (!mounted) return;
    setState(() {
      _spotifyPlaybackStatus = status['status'] as String?;
      _spotifyPlaybackReason = status['reason'] as String?;
    });
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

  Future<void> _skipTrack([double playbackPct = 35.0]) async {
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
        body: jsonEncode({'playback_pct': playbackPct}),
      );
    } catch (_) {}

    if (mounted) await _loadQueue();
  }

  void _handleYouTubePlayerEvent(YouTubePlayerEvent event) {
    switch (event.type) {
      case YouTubePlayerEventType.stateChange:
        if (event.state == YouTubePlayerState.ended) {
          _autoAdvance(playbackPctForYouTubeEvent(event));
        }
        break;
      case YouTubePlayerEventType.error:
        // Content-coverage gap (not every matched track necessarily has a
        // working embeddable video ID) — skip past it automatically rather
        // than stalling the whole session on one bad track, and tell the
        // host plainly rather than failing silently.
        _autoAdvance(playbackPctForYouTubeEvent(event));
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

  Future<void> _autoAdvance([double playbackPct = 35.0]) async {
    if (_autoAdvancePending) return;
    _autoAdvancePending = true;
    await _skipTrack(playbackPct);
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
    if (!mounted) return;

    // Always lands on the "Playback ended" screen regardless of what /close
    // did — export itself is now a manual, explicit action the host takes
    // there (Export Playlist button), not auto-triggered on arrival, so
    // there's nothing to wait on or react to here.
    context.go('/export/$_sessionId');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        // "Dismiss chevron" — same go('/home') as before, not a pop; kept
        // as an always-present leading icon (unlike other screens'
        // canPop-conditional pattern), matching the pre-existing behavior.
        leading: AppBackButton(onPressed: () => context.go('/home')),
        title: const Text('JAM Session'),
        // The AppBar previously also carried a redundant exit_to_app icon
        // that called the exact same _endSession() as the bottom "End &
        // export queue" button. Dropped in favor of mockup image 7's
        // "● LIVE" indicator here — _endSession() itself is untouched and
        // still fully reachable via the one remaining (bottom) button, so
        // this removes a duplicate entry point, not the capability itself.
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: kSpaceMd),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: const BoxDecoration(color: kPrimary, shape: BoxShape.circle),
                ),
                const SizedBox(width: kSpaceXs),
                Text('LIVE', style: kDuskTextTheme.labelSmall?.copyWith(color: kPrimary)),
              ],
            ),
          ),
        ],
      ),
      body: GradientBackground(
        child: SafeArea(
          child: _isLoading
              ? const Center(child: CircularProgressIndicator(color: kPrimary))
              : CustomScrollView(
                  // A CustomScrollView (not the previous fixed Column +
                  // Expanded(ListView)) so the banners + now-playing card
                  // and the queue list share one scroll surface: the
                  // restyled now-playing card is taller than before (the
                  // decorative Spotify placeholder), which overflowed the
                  // old fixed-height layout on shorter viewports. This was
                  // caught by re-running spotify_playback_retry_test.dart
                  // during this stage, not something touching WebSocket/
                  // playback/skip logic — SliverFillRemaining still centers
                  // "Queue is empty" correctly when content is short.
                  slivers: [
                    SliverToBoxAdapter(
                      child: Column(
                        children: [
                          // Suppressed while _stillBuildingQueue — the
                          // dedicated loading state below already covers
                          // "empty" during the grace window; showing both
                          // would just be two messages saying the same thing.
                          if (_queueBuildStatus == 'partial' ||
                              (_queueBuildStatus == 'empty' && !_stillBuildingQueue))
                            Padding(
                              padding:
                                  const EdgeInsets.fromLTRB(kSpaceMd, kSpaceSm + 4, kSpaceMd, 0),
                              child: _QueueStatusBanner(
                                status: _queueBuildStatus,
                                effectiveThreshold: _effectiveThreshold,
                              ),
                            ),
                          if (_hostPlatform == 'spotify' &&
                              (_spotifyPlaybackStatus == 'no_active_device' ||
                                  _spotifyPlaybackStatus == 'error'))
                            Padding(
                              padding:
                                  const EdgeInsets.fromLTRB(kSpaceMd, kSpaceSm + 4, kSpaceMd, 0),
                              child: AppBanner(
                                key: const Key('spotify-playback-banner'),
                                message: _spotifyPlaybackStatus == 'no_active_device'
                                    ? 'Open Spotify on your phone and play (or pause) any '
                                        'track, then retry.'
                                    : _spotifyPlaybackReason == 'SPOTIFY_REAUTH_REQUIRED'
                                        ? "Your Spotify connection expired. Reconnect to "
                                            'keep playback working.'
                                        : "Couldn't start playback on Spotify. Check your "
                                            'connection and retry.',
                                variant: AppBannerVariant.error,
                                actionLabel: _spotifyPlaybackReason == 'SPOTIFY_REAUTH_REQUIRED'
                                    ? 'Reconnect Spotify'
                                    : 'Retry',
                                actionKey: _spotifyPlaybackReason == 'SPOTIFY_REAUTH_REQUIRED'
                                    ? const Key('reconnect-spotify-button')
                                    : const Key('retry-playback-button'),
                                isActionLoading: _spotifyPlaybackReason == 'SPOTIFY_REAUTH_REQUIRED'
                                    ? false
                                    : _isRetryingPlayback,
                                onAction: _spotifyPlaybackReason == 'SPOTIFY_REAUTH_REQUIRED'
                                    ? () => context.push('/connect-platform')
                                    : _attemptSpotifyPlayback,
                              ),
                            ),
                          if (_tracks.isNotEmpty)
                            _NowPlayingCard(
                              key: ValueKey(_currentTrackId),
                              track: _tracks.first,
                              hostPlatform: _hostPlatform,
                              onYouTubeEvent: _handleYouTubePlayerEvent,
                            ),
                        ],
                      ),
                    ),
                    if (_tracks.length <= 1)
                      SliverFillRemaining(
                        hasScrollBody: false,
                        child: Center(
                          child: _stillBuildingQueue
                              ? Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: const [
                                    CircularProgressIndicator(color: kPrimary),
                                    SizedBox(height: kSpaceMd),
                                    Text(
                                      "Building your queue... this'll just take a few seconds",
                                      textAlign: TextAlign.center,
                                      style: TextStyle(color: kTextSecondary),
                                    ),
                                  ],
                                )
                              : const Text('Queue is empty', style: TextStyle(color: kTextSecondary)),
                        ),
                      )
                    else ...[
                      SliverPadding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: kSpaceMd,
                          vertical: kSpaceSm,
                        ),
                        sliver: SliverToBoxAdapter(child: _UpNextCard(track: _tracks[1])),
                      ),
                      if (_tracks.length > 2) ...[
                        SliverPadding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: kSpaceMd,
                            vertical: kSpaceSm,
                          ),
                          sliver: SliverToBoxAdapter(
                            child: Row(
                              children: [
                                Text('Up Next', style: kDuskTextTheme.titleMedium),
                                const Spacer(),
                                Text(
                                  // Same count semantics as before — total
                                  // tracks including the one currently
                                  // playing, unchanged.
                                  '${_tracks.length} tracks',
                                  style: const TextStyle(color: kTextSecondary, fontSize: 13),
                                ),
                              ],
                            ),
                          ),
                        ),
                        SliverList.builder(
                          itemCount: _tracks.length - 2,
                          itemBuilder: (context, i) => _QueueTrackTile(
                            track: _tracks[i + 2],
                            position: i + 3,
                          ),
                        ),
                      ],
                    ],
                  ],
                ),
        ),
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
// Queue status banner (Section 7) — replaces a silent empty screen with a
// concrete explanation of why the queue is short/empty. Message-selection
// logic is unchanged from before this stage; only the container is now the
// shared AppBanner.
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
    return AppBanner(message: message, variant: AppBannerVariant.info);
  }
}

// ---------------------------------------------------------------------------
// Now playing card
// ---------------------------------------------------------------------------

class _NowPlayingCard extends StatelessWidget {
  final Map<String, dynamic> track;
  final String? hostPlatform;
  final ValueChanged<YouTubePlayerEvent>? onYouTubeEvent;

  const _NowPlayingCard({
    super.key,
    required this.track,
    this.hostPlatform,
    this.onYouTubeEvent,
  });

  @override
  Widget build(BuildContext context) {
    final isYouTube = hostPlatform == 'youtube' && onYouTubeEvent != null;
    final videoId = track['track_id'] as String?;

    return Container(
      margin: const EdgeInsets.all(kSpaceMd),
      padding: const EdgeInsets.all(kSpaceMd),
      decoration: BoxDecoration(
        color: kCardAccent,
        borderRadius: BorderRadius.circular(kRadiusLg),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'NOW PLAYING',
            style: kDuskTextTheme.labelSmall?.copyWith(color: kPrimary),
          ),
          const SizedBox(height: kSpaceSm),
          if (isYouTube && videoId != null && videoId.isNotEmpty) ...[
            // Real YouTube playback — a persistent, visibly-sized IFrame
            // Player (see YouTubePlayerWidget's own doc comment on the
            // IFrame API's on-screen-visibility requirement for autoplay).
            // Untouched by this restyle: same Key, same videoId, same
            // onEvent wiring, same 200px height (unchanged deliberately —
            // this dimension is part of what keeps the player "visibly
            // on-screen" per the terms-compliance note; not something to
            // casually resize during a styling pass).
            ClipRRect(
              borderRadius: BorderRadius.circular(kRadiusMd),
              child: SizedBox(
                key: const Key('youtube-player-container'),
                height: 200,
                width: double.infinity,
                child: YouTubePlayerWidget(
                  key: ValueKey('yt-player-$videoId'),
                  videoId: videoId,
                  onEvent: onYouTubeEvent!,
                ),
              ),
            ),
          ] else
            // Spotify path has no in-app player to embed (native app
            // controls it) and, per the mockup spec, gets a decorative
            // placeholder tile instead — this app has no album-art field
            // anywhere in its data model (confirmed: QueueTrackResponse has
            // no image/cover URL), so this is a stylistic placeholder, not
            // a stand-in for real art that merely isn't loaded yet.
            Container(
              height: 200,
              width: double.infinity,
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [kGlowCoral, kPrimaryGradientStart],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(kRadiusMd),
              ),
              alignment: Alignment.center,
              child: Text(
                'cover',
                style: TextStyle(
                  color: Colors.white.withAlpha(kAlphaStrong),
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 2,
                ),
              ),
            ),
          const SizedBox(height: kSpaceMd),
          Text(
            track['title'] as String? ?? '',
            style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: kTextPrimary),
          ),
          Text(
            track['artist'] as String? ?? '',
            style: const TextStyle(color: kTextSecondary),
          ),
          const SizedBox(height: kSpaceMd),
          if (isYouTube && videoId != null && videoId.isNotEmpty)
            const Text(
              'Keep JAM AI open to keep the music playing.',
              style: TextStyle(fontSize: 11, color: kTextSecondary, fontStyle: FontStyle.italic),
            )
          else ...[
            // STILL a static placeholder value (0.35) — deliberately
            // unchanged, not "fixed" here. The backend never exposes real
            // Spotify playback position to the frontend: its Spotify
            // adapter fetches progress_ms internally
            // (get_current_playback()) but the only caller discards it —
            // it's never returned from an endpoint or broadcast over the
            // WebSocket. Making this real would mean adding new
            // backend/WebSocket data, which this stage's hard constraints
            // explicitly forbid touching. Restyled visually only.
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: const LinearProgressIndicator(
                value: 0.35,
                minHeight: 4,
                backgroundColor: kSurface,
                valueColor: AlwaysStoppedAnimation(kPrimary),
              ),
            ),
            const SizedBox(height: kSpaceXs),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('0:00', style: TextStyle(fontSize: 11, color: kTextSecondary)),
                Text(
                  _formatDuration(track['duration_ms'] as int? ?? 0),
                  style: const TextStyle(fontSize: 11, color: kTextSecondary),
                ),
              ],
            ),
          ],
          const SizedBox(height: kSpaceSm),
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
    );
  }
}

// ---------------------------------------------------------------------------
// Up next card — the immediate next track, highlighted (mockup image 7).
// Same _tracks[1] data as the old flat list's first entry; purely a display
// split, not a data change. "added by {name}" from the mockup is omitted —
// no contributor/added-by field exists anywhere in this app's track data.
// ---------------------------------------------------------------------------

class _UpNextCard extends StatelessWidget {
  final Map<String, dynamic> track;

  const _UpNextCard({required this.track});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(kSpaceMd),
      decoration: BoxDecoration(
        color: kCardSurface,
        borderRadius: BorderRadius.circular(kRadiusMd),
      ),
      child: Row(
        children: [
          const Icon(Icons.graphic_eq, color: kPrimary, size: 20),
          const SizedBox(width: kSpaceSm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Up next', style: kDuskTextTheme.labelSmall),
                const SizedBox(height: 2),
                Text(
                  track['title'] as String? ?? '',
                  style: const TextStyle(fontWeight: FontWeight.bold, color: kTextPrimary),
                ),
              ],
            ),
          ),
        ],
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
        style: const TextStyle(fontWeight: FontWeight.bold, color: kTextPrimary),
      ),
      subtitle: Text(track['artist'] as String? ?? '', style: const TextStyle(color: kTextSecondary)),
      trailing: Text(
        _formatDuration(track['duration_ms'] as int? ?? 0),
        style: const TextStyle(color: kTextSecondary, fontSize: 12),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Player controls — this app has exactly one real playback-affecting
// action from here (Skip, to the next track; native Spotify/YouTube
// playback itself isn't controlled from this app). The mockup's
// skip-back/play-pause/skip-forward trio doesn't map onto real
// functionality this app has, so only the one real action is represented —
// as a prominent circular button, matching the mockup's visual weight for
// its central control — rather than adding non-functional buttons for
// capabilities that don't exist. onSkip/onEnd are passed through unchanged.
// ---------------------------------------------------------------------------

class _PlayerControls extends StatelessWidget {
  final VoidCallback onSkip;
  final VoidCallback onEnd;

  const _PlayerControls({required this.onSkip, required this.onEnd});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: kBackground,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: kSpaceLg, vertical: kSpaceMd),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              GestureDetector(
                onTap: onSkip,
                child: Container(
                  width: 64,
                  height: 64,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: const LinearGradient(colors: kPrimaryGradient),
                    boxShadow: [
                      BoxShadow(
                        color: kPrimaryGradientStart.withAlpha(kAlphaMedium),
                        blurRadius: 20,
                        offset: const Offset(0, 6),
                      ),
                    ],
                  ),
                  child: const Icon(Icons.skip_next, color: Colors.white, size: 32),
                ),
              ),
              const SizedBox(height: kSpaceMd),
              SecondaryButton(label: 'End & export queue', onPressed: onEnd),
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
