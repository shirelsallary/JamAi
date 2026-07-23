import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../../../core/youtube_player_event.dart';

/// Real YouTube playback — a persistent WebView embedding YouTube's public
/// IFrame Player API (a completely separate thing from ytmusicapi, which has
/// no playback capability at all). This is a genuinely new subsystem, not an
/// extension of youtube_webview_screen.dart (the one-shot cookie-connection
/// screen, which navigates away and disposes after connecting) — nothing
/// from that screen is reused beyond the webview_flutter dependency.
///
/// Foreground-only by design: the IFrame API's own terms require the player
/// to be visibly on-screen before autoplay, and background/screen-off
/// playback for embedded players is a known, current limitation (YouTube
/// has been restricting background playback to Premium subscribers in
/// third-party/embedded contexts) that this project explicitly does not
/// attempt to solve — see the foreground-only notice in session_screen.dart.
class YouTubePlayerWidget extends StatefulWidget {
  final String videoId;
  final ValueChanged<YouTubePlayerEvent> onEvent;

  const YouTubePlayerWidget({
    super.key,
    required this.videoId,
    required this.onEvent,
  });

  @override
  State<YouTubePlayerWidget> createState() => _YouTubePlayerWidgetState();
}

class _YouTubePlayerWidgetState extends State<YouTubePlayerWidget> {
  late final WebViewController _controller;
  bool _isReady = false;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.black)
      ..addJavaScriptChannel('YtBridge', onMessageReceived: _handleMessage)
      ..loadHtmlString(_playerHtml, baseUrl: 'https://jamai-lpjq.onrender.com');
  }

  void _handleMessage(JavaScriptMessage message) {
    final event = YouTubePlayerEvent.fromJson(message.message);
    if (event == null) return;

    if (event.type == YouTubePlayerEventType.ready) {
      _isReady = true;
      _loadVideo(widget.videoId);
    }
    widget.onEvent(event);
  }

  void _loadVideo(String videoId) {
    _controller.runJavaScript(
      "jamaiLoadVideo('${escapeForJsStringLiteral(videoId)}')",
    );
  }

  @override
  void didUpdateWidget(YouTubePlayerWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.videoId != oldWidget.videoId && _isReady) {
      _loadVideo(widget.videoId);
    }
  }

  @override
  Widget build(BuildContext context) {
    return WebViewWidget(controller: _controller);
  }
}

// A minimal page: loads the IFrame Player API, creates a player targeting
// #player, and relays onReady/onStateChange/onError back to Dart via the
// YtBridge JavaScriptChannel as small JSON messages (see
// core/youtube_player_event.dart for the Dart-side parser). jamaiLoadVideo
// queues a video ID if called before the player is ready, since Dart may
// set widget.videoId before onYouTubeIframeAPIReady has fired.
const String _playerHtml = '''
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
  <style>html,body,#player{margin:0;padding:0;width:100%;height:100%;background:#000;}</style>
</head>
<body>
<div id="player"></div>
<script>
  var player;
  var pendingVideoId = null;
  var isReady = false;

  function onYouTubeIframeAPIReady() {
    player = new YT.Player('player', {
      height: '100%',
      width: '100%',
      playerVars: { playsinline: 1, controls: 1, rel: 0 },
      events: {
        'onReady': onPlayerReady,
        'onStateChange': onPlayerStateChange,
        'onError': onPlayerError
      }
    });
  }

  function onPlayerReady(event) {
    isReady = true;
    YtBridge.postMessage(JSON.stringify({type: 'ready'}));
    if (pendingVideoId) {
      player.loadVideoById(pendingVideoId);
      pendingVideoId = null;
    }
  }

  function onPlayerStateChange(event) {
    var stateNames = {'-1': 'unstarted', '0': 'ended', '1': 'playing', '2': 'paused', '3': 'buffering', '5': 'cued'};
    var name = stateNames[String(event.data)] || 'unknown';
    YtBridge.postMessage(JSON.stringify({type: 'state_change', state: name}));
  }

  function onPlayerError(event) {
    YtBridge.postMessage(JSON.stringify({type: 'error', code: event.data}));
  }

  function jamaiLoadVideo(videoId) {
    if (isReady && player && player.loadVideoById) {
      player.loadVideoById(videoId);
    } else {
      pendingVideoId = videoId;
    }
  }

  var tag = document.createElement('script');
  tag.src = "https://www.youtube.com/iframe_api";
  var firstScriptTag = document.getElementsByTagName('script')[0];
  firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
</script>
</body>
</html>
''';
