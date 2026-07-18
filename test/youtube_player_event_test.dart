// YouTube IFrame Player JS bridge — message-parsing logic only. The actual
// WebView/IFrame rendering isn't exercised here (no platform-channel binding
// in flutter_test, same constraint as every other WebView-based screen in
// this app) — see youtube_player_widget.dart's own doc comment.

import 'package:flutter_test/flutter_test.dart';
import 'package:jam_ai_app/core/youtube_player_event.dart';

void main() {
  group('YouTubePlayerEvent.fromJson', () {
    test('parses a ready event', () {
      final event = YouTubePlayerEvent.fromJson('{"type":"ready"}');
      expect(event, isNotNull);
      expect(event!.type, YouTubePlayerEventType.ready);
    });

    test('parses a state_change event for every known state', () {
      const cases = {
        'unstarted': YouTubePlayerState.unstarted,
        'ended': YouTubePlayerState.ended,
        'playing': YouTubePlayerState.playing,
        'paused': YouTubePlayerState.paused,
        'buffering': YouTubePlayerState.buffering,
        'cued': YouTubePlayerState.cued,
      };
      for (final entry in cases.entries) {
        final event = YouTubePlayerEvent.fromJson(
          '{"type":"state_change","state":"${entry.key}"}',
        );
        expect(event!.type, YouTubePlayerEventType.stateChange);
        expect(event.state, entry.value, reason: 'state=${entry.key}');
      }
    });

    test('an unrecognized state string maps to unknown, not a crash', () {
      final event = YouTubePlayerEvent.fromJson(
        '{"type":"state_change","state":"something_new"}',
      );
      expect(event!.state, YouTubePlayerState.unknown);
    });

    test('parses an error event with its code', () {
      final event = YouTubePlayerEvent.fromJson('{"type":"error","code":150}');
      expect(event!.type, YouTubePlayerEventType.error);
      expect(event.errorCode, 150);
    });

    test('returns null for an unrecognized top-level type', () {
      expect(YouTubePlayerEvent.fromJson('{"type":"something_else"}'), isNull);
    });

    test('returns null for malformed JSON rather than throwing', () {
      expect(YouTubePlayerEvent.fromJson('not json at all'), isNull);
      expect(YouTubePlayerEvent.fromJson(''), isNull);
      expect(YouTubePlayerEvent.fromJson('[]'), isNull);
      expect(YouTubePlayerEvent.fromJson('{}'), isNull);
    });
  });

  group('escapeForJsStringLiteral', () {
    test('escapes single quotes and backslashes', () {
      expect(escapeForJsStringLiteral("it's"), "it\\'s");
      expect(escapeForJsStringLiteral(r'a\b'), r'a\\b');
    });

    test('leaves a normal video ID untouched', () {
      expect(escapeForJsStringLiteral('dQw4w9WgXcQ'), 'dQw4w9WgXcQ');
    });
  });
}
