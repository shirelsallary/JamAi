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
import '../../../core/widgets/widgets.dart';

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

  // UI-only — which platform's row shows the connection/selection glow.
  // Not read by any OAuth/deep-link logic below; set synchronously (before
  // any await) at the start of each platform's tap handler so the glow
  // reacts immediately, and never cleared in-place since a successful
  // connection always navigates away from this screen.
  AppPlatform? _selectedPlatform;

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
    setState(() => _selectedPlatform = AppPlatform.spotify);

    final isAndroid = defaultTargetPlatform == TargetPlatform.android;

    // Hard block, not a routing decision (reversed from the earlier Bug 2
    // fix's behavior — see spotify_app_to_app_test.dart). Checked before any
    // network call: the app must never reach GET /oauth/spotify at all when
    // Spotify isn't installed, and there is no browser fallback from here —
    // only an "Install Spotify" dialog action.
    if (isAndroid && !await SpotifyAppAuth.isSpotifyInstalled()) {
      if (!mounted) return;
      await _showSpotifyNotInstalledDialog();
      return;
    }

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

      // isAndroid here already implies Spotify is installed — the hard
      // block above returned early otherwise.
      if (isAndroid) {
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

  Future<void> _showSpotifyNotInstalledDialog() async {
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Spotify not installed'),
        content: const Text(
          "Spotify isn't installed on this device. Install it to connect.",
        ),
        actions: [
          TextButton(
            key: const Key('install-spotify-button'),
            onPressed: () {
              Navigator.of(dialogContext).pop();
              launchUrl(
                Uri.parse(kSpotifyPlayStoreUrl),
                mode: LaunchMode.externalApplication,
              );
            },
            child: const Text('Install Spotify'),
          ),
        ],
      ),
    );
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
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Connect Platform'),
        leading: Navigator.canPop(context)
            ? AppBackButton(onPressed: () => context.pop())
            : null,
      ),
      body: GradientBackground(
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(kSpaceLg),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Center(
                  child: Container(
                    width: 72,
                    height: 72,
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(colors: kPrimaryGradient),
                      borderRadius: BorderRadius.circular(kRadiusLg),
                      boxShadow: [
                        BoxShadow(
                          color: kPrimaryGradientStart.withAlpha(kAlphaMedium),
                          blurRadius: 24,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    child: const Icon(Icons.music_note, size: 32, color: Colors.white),
                  ),
                ),
                const SizedBox(height: kSpaceMd),
                Text(
                  'Connect your music',
                  textAlign: TextAlign.center,
                  style: kDuskTextTheme.headlineMedium,
                ),
                const SizedBox(height: kSpaceSm),
                const Text(
                  'Choose the platform you use to listen to music',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 14, color: kTextSecondary),
                ),
                const SizedBox(height: kSpaceXxl),
                _PlatformConnectButton(
                  key: const Key('connect-spotify-button'),
                  label: 'Connect Spotify',
                  color: kGreen,
                  isSelected: _selectedPlatform == AppPlatform.spotify,
                  onTap: _isConnecting ? null : _connectSpotify,
                ),
                const SizedBox(height: kSpaceMd),
                _PlatformConnectButton(
                  key: const Key('connect-youtube-button'),
                  label: 'Connect YouTube Music',
                  // kYouTubeRed (brand token), not kRed (error token) — see
                  // theme.dart's token-separation notes from the Dusk
                  // redesign foundation.
                  color: kYouTubeRed,
                  isSelected: _selectedPlatform == AppPlatform.youtube,
                  onTap: _isConnecting
                      ? null
                      : () {
                          setState(() => _selectedPlatform = AppPlatform.youtube);
                          // Bug 2 fix — used to show a blocking "unsupported"
                          // dialog even though YouTubeWebViewScreen already
                          // exists and works; it was simply unreachable.
                          // push (not go) so the back button on
                          // YouTubeWebViewScreen has somewhere to return to.
                          context.push('/youtube-connect');
                        },
                ),
                const SizedBox(height: kSpaceLg),
                if (_error != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: kSpaceSm + 4),
                    child: AppBanner(message: _error!, variant: AppBannerVariant.error),
                  ),
                if (_appToAppError != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: kSpaceSm + 4),
                    child: AppBanner(
                      message: _appToAppError!,
                      variant: AppBannerVariant.error,
                      actionLabel: 'Use browser instead',
                      actionKey: const Key('use-browser-instead-button'),
                      onAction: _isConnecting ? null : _useBrowserInstead,
                    ),
                  ),
                if (_showVerifyButton)
                  PrimaryButton(
                    label: 'Already connected? Refresh',
                    onPressed: _isConnecting ? null : _verifyAndContinue,
                    isLoading: _isConnecting,
                  ),
                TextButton(
                  onPressed: () => context.go('/home'),
                  style: TextButton.styleFrom(foregroundColor: kTextSecondary),
                  child: const Text('Skip for now'),
                ),
              ],
            ),
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
  // Glow reflects live selection/connection state (which platform the user
  // most recently tapped/attempted), driven by ConnectPlatformScreen's
  // _selectedPlatform — not a static per-platform identity. Both rows are
  // always tappable regardless of this value.
  final bool isSelected;

  const _PlatformConnectButton({
    super.key,
    required this.label,
    required this.color,
    required this.onTap,
    this.isSelected = false,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Opacity(
        opacity: onTap == null ? 0.5 : 1.0,
        child: Container(
          padding: const EdgeInsets.all(kSpaceMd),
          decoration: BoxDecoration(
            color: color.withAlpha(kAlphaSoft),
            borderRadius: BorderRadius.circular(kRadiusMd),
            border: Border.all(color: color, width: 1.5),
            boxShadow: isSelected
                ? [
                    BoxShadow(
                      color: color.withAlpha(kAlphaMedium),
                      blurRadius: 16,
                      spreadRadius: 1,
                    ),
                  ]
                : null,
          ),
          child: Row(
            children: [
              Container(
                width: 16,
                height: 16,
                decoration: BoxDecoration(color: color, shape: BoxShape.circle),
              ),
              const SizedBox(width: kSpaceSm),
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
