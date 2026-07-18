import 'dart:async';
import 'dart:convert';
import 'package:app_links/app_links.dart';
import 'package:flutter/foundation.dart' show defaultTargetPlatform, TargetPlatform;
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/spotify_app_auth.dart';
import '../../../core/theme.dart';

class ConnectPlatformScreen extends StatefulWidget {
  const ConnectPlatformScreen({super.key});

  @override
  State<ConnectPlatformScreen> createState() => _ConnectPlatformScreenState();
}

class _ConnectPlatformScreenState extends State<ConnectPlatformScreen> {
  bool _isConnecting = false;
  bool _showVerifyButton = false;
  String? _error;

  // App-to-App (Spotify Android app installed) specific failure state — kept
  // separate from _error/_showVerifyButton (the pre-existing browser-flow
  // states) since App-to-App failure needs its own "Use browser instead"
  // manual fallback, not the "Already connected? Refresh" one.
  String? _appToAppError;
  String? _pendingAuthorizeUrl;

  AppLinks? _appLinks;
  StreamSubscription<Uri>? _linkSubscription;

  @override
  void initState() {
    super.initState();
    // Bug 2 fix — listen for the jamai://spotify-callback deep link Spotify
    // redirects to after the user approves in the external browser. Wrapped
    // defensively: platforms/environments without deep-link channel support
    // (e.g. widget tests, or a desktop target with no plugin registered)
    // must not crash the screen — Spotify connect still works via the
    // "Already connected? Refresh" manual fallback in that case.
    //
    // KNOWN GAP (deferred by product decision, not forgotten): this only
    // catches the deep link while ConnectPlatformScreen is already mounted
    // (uriLinkStream, a "warm" listener). If the OS kills/backgrounds the app
    // while the user is in Spotify's browser and the deep link arrives to a
    // freshly cold-started app instance, this listener isn't attached yet and
    // the redirect is silently missed — the same failure mode Bug 2 fixed for
    // the general case, just narrowed to cold start. app_links' getInitialLink()
    // is the fix for that (check it once at app startup, not just this
    // screen), not implemented here. The manual "Already connected? Refresh"
    // fallback below is the stopgap until that's built.
    try {
      _appLinks = AppLinks();
      _linkSubscription = _appLinks!.uriLinkStream.listen(
        _handleDeepLink,
        onError: (_) {},
      );
    } catch (_) {
      // no deep-link support on this platform — manual fallback still works
    }
  }

  @override
  void dispose() {
    _linkSubscription?.cancel();
    super.dispose();
  }

  Future<void> _handleDeepLink(Uri uri) async {
    if (uri.scheme != 'jamai' || uri.host != 'spotify-callback') return;

    final error = uri.queryParameters['error'];
    if (error != null) {
      if (mounted) {
        setState(() => _error = 'Spotify connection was cancelled or denied.');
      }
      return;
    }

    final code = uri.queryParameters['code'];
    final state = uri.queryParameters['state'];
    if (code == null || state == null) return;

    setState(() {
      _isConnecting = true;
      _error = null;
    });

    try {
      final token = await AuthService.getToken();
      if (token == null) {
        if (mounted) context.go('/');
        return;
      }

      final response = await http.post(
        Uri.parse('$kBaseUrl/auth/oauth/spotify/exchange'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({'code': code, 'state': state}),
      );
      if (!mounted) return;

      if (response.statusCode == 200) {
        // Success path — no manual "I connected my account" tap needed.
        context.go('/home');
      } else {
        setState(() => _error = 'Could not complete Spotify connection. Try again.');
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'Connection failed. Please try again.');
    } finally {
      if (mounted) setState(() => _isConnecting = false);
    }
  }

  Future<void> _connectSpotify() async {
    final token = await AuthService.getToken();
    if (!mounted) return;
    if (token == null) {
      context.go('/');
      return;
    }

    setState(() {
      _isConnecting = true;
      _appToAppError = null;
    });

    try {
      // Bug 2 fix — this call is authenticated (normal Bearer header, made
      // from inside the app) and only returns the authorize URL; the JWT
      // itself never reaches the external browser. Both the App-to-App and
      // browser paths below reuse this same response — App-to-App parses
      // client_id/scope/state/redirect_uri out of it instead of duplicating
      // them client-side, so there is exactly one source of truth for scopes
      // and exactly one (single-use) state token generated per attempt.
      final response = await http.get(
        Uri.parse('$kBaseUrl/auth/oauth/spotify'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (!mounted) return;
      if (response.statusCode != 200) {
        throw Exception('Failed to start Spotify connection');
      }

      final data = jsonDecode(response.body) as Map<String, dynamic>;
      final authorizeUrlString = data['authorize_url'] as String;
      _pendingAuthorizeUrl = authorizeUrlString;

      // Not-installed is a routing decision, not a failure — falls straight
      // through to the existing browser flow below with no user-facing
      // difference. Only an App-to-App attempt that actually starts (Spotify
      // installed) and then fails/is cancelled shows an explicit error.
      final useAppToApp = defaultTargetPlatform == TargetPlatform.android &&
          await SpotifyAppAuth.isSpotifyInstalled();

      if (useAppToApp) {
        final params = SpotifyAuthorizeParams.fromAuthorizeUrl(authorizeUrlString);
        if (params != null) {
          await _attemptAppToApp(token, params);
          return;
        }
        // authorize_url always carries these params in practice (the backend
        // always includes them) — falling through to the browser flow is a
        // safe default if that ever isn't true, rather than blocking connection.
      }

      await _openAuthorizeUrlInBrowser(authorizeUrlString);
    } catch (_) {
      if (!mounted) return;
      setState(() => _isConnecting = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not open Spotify. Please try again.'),
          backgroundColor: kRed,
          duration: Duration(seconds: 4),
        ),
      );
    }
  }

  Future<void> _openAuthorizeUrlInBrowser(String authorizeUrlString) async {
    final authorizeUrl = Uri.parse(authorizeUrlString);
    if (await canLaunchUrl(authorizeUrl)) {
      await launchUrl(authorizeUrl, mode: LaunchMode.externalApplication);
      if (!mounted) return;
      setState(() {
        _isConnecting = false;
        _showVerifyButton = true;
      });
    } else {
      throw Exception('Cannot launch URL');
    }
  }

  Future<void> _attemptAppToApp(String token, SpotifyAuthorizeParams params) async {
    final result = await SpotifyAppAuth.authorize(
      clientId: params.clientId,
      redirectUri: params.redirectUri,
      scopes: params.scopes,
      state: params.state,
    );
    if (!mounted) return;

    if (!result.isSuccess) {
      // Covers both cancellation and a hard error — per spec, an App-to-App
      // attempt that doesn't end in a connected account always surfaces an
      // explicit error with a manual fallback, never a silent retry or a
      // silent drop back to the browser flow.
      setState(() {
        _isConnecting = false;
        _appToAppError = result.isCancelled
            ? 'Spotify connection was cancelled.'
            : 'Could not connect with the Spotify app.';
      });
      return;
    }

    try {
      final response = await http.post(
        Uri.parse('$kBaseUrl/auth/oauth/spotify/exchange'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'code': result.code,
          'state': result.state ?? params.state,
        }),
      );
      if (!mounted) return;

      if (response.statusCode == 200) {
        context.go('/home');
      } else {
        setState(() {
          _isConnecting = false;
          _appToAppError = 'Could not connect with the Spotify app.';
        });
      }
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isConnecting = false;
        _appToAppError = 'Could not connect with the Spotify app.';
      });
    }
  }

  Future<void> _useBrowserInstead() async {
    final authorizeUrlString = _pendingAuthorizeUrl;
    if (authorizeUrlString == null) {
      // Shouldn't happen (this button only shows after a successful fetch
      // set it) — re-run the full flow rather than leaving the button inert.
      await _connectSpotify();
      return;
    }

    setState(() {
      _appToAppError = null;
      _isConnecting = true;
    });

    try {
      await _openAuthorizeUrlInBrowser(authorizeUrlString);
    } catch (_) {
      if (!mounted) return;
      setState(() => _isConnecting = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Could not open Spotify. Please try again.'),
          backgroundColor: kRed,
          duration: Duration(seconds: 4),
        ),
      );
    }
  }

  Future<void> _verifyAndContinue() async {
    // Manual fallback only (per Bug 2 fix) — the deep-link handler above is
    // the primary success path. Kept in case the OS fails to deliver the
    // deep link back to the app (device quirk / user backgrounded the app).
    setState(() {
      _isConnecting = true;
      _error = null;
    });

    try {
      final token = await AuthService.getToken();
      if (token == null) {
        if (mounted) context.go('/');
        return;
      }
      final me = await AuthService.getMe(token);
      if (!mounted) return;

      final platformToken = me?['platform_token'];
      if (platformToken != null && platformToken.toString().isNotEmpty) {
        context.go('/home');
      } else {
        setState(() => _error = 'Platform not connected yet. Try again.');
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'Connection failed. Please try again.');
    } finally {
      if (mounted) setState(() => _isConnecting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBackground,
      appBar: AppBar(
        title: const Text('Connect Platform'),
        leading: Navigator.canPop(context)
            ? IconButton(
                icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
                onPressed: () => context.pop(),
              )
            : null,
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(Icons.music_note, size: 64, color: kPrimary),
              const SizedBox(height: 16),
              const Text(
                'Connect your music',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  color: kTextPrimary,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Choose the platform you use to listen to music',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 14, color: kTextSecondary),
              ),
              const SizedBox(height: 48),
              _PlatformConnectButton(
                key: const Key('connect-spotify-button'),
                label: 'Connect Spotify',
                color: kGreen,
                onTap: _isConnecting ? null : _connectSpotify,
              ),
              const SizedBox(height: 16),
              _PlatformConnectButton(
                key: const Key('connect-youtube-button'),
                label: 'Connect YouTube Music',
                color: kRed,
                // Bug 2 fix — used to show a blocking "unsupported" dialog
                // even though YouTubeWebViewScreen already exists and works;
                // it was simply unreachable. push (not go) so the back
                // button on YouTubeWebViewScreen has somewhere to return to.
                onTap: _isConnecting ? null : () => context.push('/youtube-connect'),
              ),
              const SizedBox(height: 24),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Text(
                    _error!,
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: kRed, fontSize: 12),
                  ),
                ),
              if (_appToAppError != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Column(
                    children: [
                      Text(
                        _appToAppError!,
                        textAlign: TextAlign.center,
                        style: const TextStyle(color: kRed, fontSize: 12),
                      ),
                      const SizedBox(height: 8),
                      TextButton(
                        key: const Key('use-browser-instead-button'),
                        onPressed: _isConnecting ? null : _useBrowserInstead,
                        child: const Text('Use browser instead'),
                      ),
                    ],
                  ),
                ),
              if (_showVerifyButton)
                ElevatedButton(
                  onPressed: _isConnecting ? null : _verifyAndContinue,
                  child: _isConnecting
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: Colors.white,
                          ),
                        )
                      : const Text('Already connected? Refresh'),
                ),
              TextButton(
                onPressed: () => context.go('/home'),
                child: const Text('Skip for now'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Platform connect button
// ---------------------------------------------------------------------------

class _PlatformConnectButton extends StatelessWidget {
  final String label;
  final Color color;
  final VoidCallback? onTap;

  const _PlatformConnectButton({
    super.key,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Opacity(
        opacity: onTap == null ? 0.5 : 1.0,
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: color.withAlpha(20),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color, width: 1.5),
          ),
          child: Row(
            children: [
              Container(
                width: 16,
                height: 16,
                decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              ),
              const SizedBox(width: 8),
              Text(
                label,
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
              const Spacer(),
              Icon(Icons.arrow_forward_ios, size: 16, color: color),
            ],
          ),
        ),
      ),
    );
  }
}
