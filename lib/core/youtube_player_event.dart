import 'dart:convert';

/// Parses the JSON messages sent by the YouTube IFrame Player API JS bridge
/// (see youtube_player_widget.dart's embedded HTML) back into Dart. Kept as
/// a pure function/class — no WebView dependency — so the message-parsing
/// logic itself is unit-testable; the actual WebView/IFrame rendering isn't
/// (flutter_test has no platform-channel binding for it).
enum YouTubePlayerEventType { ready, stateChange, error, unknown }

enum YouTubePlayerState { unstarted, ended, playing, paused, buffering, cued, unknown }

class YouTubePlayerEvent {
  final YouTubePlayerEventType type;
  final YouTubePlayerState? state;
  final int? errorCode;

  const YouTubePlayerEvent._({required this.type, this.state, this.errorCode});

  /// Returns null for anything unparseable — callers should silently ignore
  /// rather than crash on a malformed/unexpected message from the JS side.
  static YouTubePlayerEvent? fromJson(String raw) {
    final Map<String, dynamic> data;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) return null;
      data = decoded;
    } catch (_) {
      return null;
    }

    switch (data['type'] as String?) {
      case 'ready':
        return const YouTubePlayerEvent._(type: YouTubePlayerEventType.ready);
      case 'state_change':
        return YouTubePlayerEvent._(
          type: YouTubePlayerEventType.stateChange,
          state: _parseState(data['state'] as String?),
        );
      case 'error':
        return YouTubePlayerEvent._(
          type: YouTubePlayerEventType.error,
          errorCode: data['code'] as int?,
        );
      default:
        return null;
    }
  }

  static YouTubePlayerState _parseState(String? raw) {
    switch (raw) {
      case 'unstarted':
        return YouTubePlayerState.unstarted;
      case 'ended':
        return YouTubePlayerState.ended;
      case 'playing':
        return YouTubePlayerState.playing;
      case 'paused':
        return YouTubePlayerState.paused;
      case 'buffering':
        return YouTubePlayerState.buffering;
      case 'cued':
        return YouTubePlayerState.cued;
      default:
        return YouTubePlayerState.unknown;
    }
  }
}

/// Escapes a video ID for safe injection into a single-quoted JS string
/// literal (see jamaiLoadVideo(...) calls in youtube_player_widget.dart).
/// YouTube video IDs are always [A-Za-z0-9_-]{11}, but this doesn't assume
/// that — it defends against a malformed track_id breaking the injected
/// script rather than trusting the format.
String escapeForJsStringLiteral(String value) {
  return value.replaceAll('\\', '\\\\').replaceAll("'", "\\'");
}
