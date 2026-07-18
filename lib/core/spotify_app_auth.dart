import 'package:flutter/services.dart';

/// Result of an App-to-App Spotify authorization attempt via the native
/// bridge in MainActivity.kt (com.spotify.android:auth's AuthorizationClient).
class SpotifyAppAuthResult {
  final String _type; // 'code' | 'error' | 'cancelled'
  final String? code;
  final String? state;
  final String? error;

  const SpotifyAppAuthResult._(this._type, {this.code, this.state, this.error});

  factory SpotifyAppAuthResult.code(String code, String? state) =>
      SpotifyAppAuthResult._('code', code: code, state: state);
  factory SpotifyAppAuthResult.cancelled() => const SpotifyAppAuthResult._('cancelled');
  factory SpotifyAppAuthResult.error(String message) =>
      SpotifyAppAuthResult._('error', error: message);

  bool get isSuccess => _type == 'code';
  bool get isCancelled => _type == 'cancelled';
}

/// Bridges to the native (Android-only) Spotify Auth SDK — AuthorizationClient
/// — via the platform channel set up in MainActivity.kt. Every method here is
/// Android-only; callers must gate on Platform.isAndroid first.
class SpotifyAppAuth {
  static const MethodChannel _channel = MethodChannel('jamai/spotify_app_auth');

  static Future<bool> isSpotifyInstalled() async {
    try {
      final result = await _channel.invokeMethod<bool>('isSpotifyInstalled');
      return result ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  static Future<SpotifyAppAuthResult> authorize({
    required String clientId,
    required String redirectUri,
    required List<String> scopes,
    required String state,
  }) async {
    try {
      final raw = await _channel.invokeMethod<dynamic>('authorize', {
        'clientId': clientId,
        'redirectUri': redirectUri,
        'scopes': scopes,
        'state': state,
      });
      final result = (raw as Map?)?.cast<String, dynamic>();
      final type = result?['type'] as String?;
      switch (type) {
        case 'code':
          final code = result?['code'] as String?;
          if (code == null) {
            return SpotifyAppAuthResult.error('Spotify authorization returned no code.');
          }
          return SpotifyAppAuthResult.code(code, result?['state'] as String?);
        case 'cancelled':
          return SpotifyAppAuthResult.cancelled();
        default:
          return SpotifyAppAuthResult.error(
            result?['error'] as String? ?? 'Spotify authorization failed.',
          );
      }
    } on PlatformException catch (e) {
      return SpotifyAppAuthResult.error(e.message ?? 'Spotify authorization failed.');
    } on MissingPluginException {
      return SpotifyAppAuthResult.error('Spotify authorization is unavailable.');
    }
  }
}

/// Pure — parses client_id/redirect_uri/scope/state off the authorize_url
/// GET /auth/oauth/spotify already returns, so the App-to-App path reuses the
/// exact same values (and the same server-generated, single-use state token)
/// the browser flow uses, instead of duplicating them client-side.
class SpotifyAuthorizeParams {
  final String clientId;
  final String redirectUri;
  final List<String> scopes;
  final String state;

  const SpotifyAuthorizeParams({
    required this.clientId,
    required this.redirectUri,
    required this.scopes,
    required this.state,
  });

  static SpotifyAuthorizeParams? fromAuthorizeUrl(String authorizeUrl) {
    final uri = Uri.parse(authorizeUrl);
    final clientId = uri.queryParameters['client_id'];
    final redirectUri = uri.queryParameters['redirect_uri'];
    final scope = uri.queryParameters['scope'];
    final state = uri.queryParameters['state'];
    if (clientId == null ||
        redirectUri == null ||
        scope == null ||
        scope.isEmpty ||
        state == null) {
      return null;
    }
    return SpotifyAuthorizeParams(
      clientId: clientId,
      redirectUri: redirectUri,
      scopes: scope.split(' '),
      state: state,
    );
  }
}
