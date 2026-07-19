import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:mobile_scanner/mobile_scanner.dart';
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/deep_link_utils.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

class JoinSessionScreen extends StatefulWidget {
  // Populated when this screen is reached via a jamai://join/{code} deep
  // link (QR code scan or shared link) — see main.dart's deep-link listener.
  final String? initialCode;

  const JoinSessionScreen({super.key, this.initialCode});

  @override
  State<JoinSessionScreen> createState() => _JoinSessionScreenState();
}

class _JoinSessionScreenState extends State<JoinSessionScreen> {
  late final TextEditingController _codeController;
  String _code = '';
  bool _isLoading = false;
  String? _error;

  // Section 0 — the guest's own connected platform, independent of the
  // host's. Auto-selected (at most one connected platform per account today).
  bool _loadingPlatform = true;
  String? _selectedPlatform;

  // In-app camera scanner (Stage E) — a second, additional way to arrive at
  // a join code, alongside manual entry and the pre-existing
  // jamai://join/{code} OS-level deep link (main.dart). Detected codes are
  // parsed with the exact same parseJoinCode() the deep-link listener uses
  // (core/deep_link_utils.dart), and a successful scan calls _joinSession()
  // — the exact same method the manual "Join" button calls. Neither the
  // deep-link path nor _joinSession() itself is modified by any of this.
  late final MobileScannerController _scannerController;
  bool _isProcessingScan = false;

  @override
  void initState() {
    super.initState();
    final prefill = widget.initialCode?.toUpperCase() ?? '';
    _code = prefill;
    _codeController = TextEditingController(text: prefill);
    _scannerController = MobileScannerController(detectionSpeed: DetectionSpeed.noDuplicates);
    _loadSelectedPlatform();
  }

  @override
  void dispose() {
    _codeController.dispose();
    _scannerController.dispose();
    super.dispose();
  }

  Future<void> _loadSelectedPlatform() async {
    final token = await AuthService.getToken();
    if (!mounted) return;
    if (token == null) {
      context.go('/');
      return;
    }
    final me = await AuthService.getMe(token);
    if (!mounted) return;
    final platform = me?['platform'] as String?;
    final platformToken = me?['platform_token'] as String?;
    setState(() {
      _selectedPlatform =
          (platform != null && platformToken != null && platformToken.isNotEmpty)
              ? platform
              : null;
      _loadingPlatform = false;
    });
  }

  Future<void> _joinSession() async {
    if (_selectedPlatform == null) return;
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final token = await AuthService.getToken();
      if (!mounted) return;
      if (token == null) {
        context.go('/');
        return;
      }

      final response = await http.get(
        Uri.parse('$kBaseUrl/sessions/$_code/join?selected_platform=$_selectedPlatform'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (!mounted) return;

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        context.go('/session/${data['session_id']}');
      } else if (response.statusCode == 409) {
        setState(() => _error = 'You are already in this session');
      } else if (response.statusCode == 404) {
        setState(() =>
            _error = 'Session not found. Check the code and try again.');
      } else {
        setState(() => _error = 'Could not join session. Please try again.');
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Could not join session. Please try again.');
      }
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  // Parses a scanned barcode's raw content with the exact same
  // parseJoinCode() the OS-level jamai://join/{code} deep-link listener
  // uses (main.dart's _handleDeepLink), so both paths agree on what counts
  // as a valid join code by construction, not by keeping two parsers in
  // sync by hand. On a valid match, prefills the code field (mirroring
  // initState's deep-link prefill) and calls _joinSession() — the same
  // method the manual "Join" button calls, unmodified.
  Future<void> _handleBarcodeDetected(BarcodeCapture capture) async {
    if (_isProcessingScan) return;

    for (final barcode in capture.barcodes) {
      final raw = barcode.rawValue;
      if (raw == null) continue;
      final uri = Uri.tryParse(raw);
      if (uri == null) continue;
      final code = parseJoinCode(uri);
      if (code == null) continue;

      setState(() {
        _isProcessingScan = true;
        _code = code;
        _codeController.text = code;
      });
      await _scannerController.stop();
      await _joinSession();
      if (!mounted) return;

      if (_error != null) {
        // Join failed (stale/invalid/already-in code, etc.) — restart the
        // camera so the user can try scanning again rather than stranding
        // them on a frozen preview; the manual field below still works too.
        setState(() => _isProcessingScan = false);
        await _scannerController.start();
      }
      break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Join JAM'),
        leading: Navigator.canPop(context)
            ? AppBackButton(onPressed: () => context.pop())
            : null,
      ),
      body: GradientBackground(
        child: SafeArea(
          child: _loadingPlatform
              ? const Center(child: CircularProgressIndicator(color: kPrimary))
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(kSpaceLg),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(kRadiusLg),
                        child: SizedBox(
                          key: const Key('qr-scanner-view'),
                          height: 260,
                          child: MobileScanner(
                            controller: _scannerController,
                            onDetect: _handleBarcodeDetected,
                            overlayBuilder: (context, constraints) => const _ScannerOverlay(),
                            errorBuilder: (context, error, child) {
                              final message =
                                  error.errorCode == MobileScannerErrorCode.permissionDenied
                                      ? 'Camera permission denied. Enable it in Settings, '
                                          'or enter the code below.'
                                      : 'Camera unavailable. Enter the code below instead.';
                              return Container(
                                color: kSurface,
                                alignment: Alignment.center,
                                padding: const EdgeInsets.all(kSpaceMd),
                                child: Text(
                                  message,
                                  textAlign: TextAlign.center,
                                  style: const TextStyle(color: kTextSecondary, fontSize: 13),
                                ),
                              );
                            },
                          ),
                        ),
                      ),
                      const SizedBox(height: kSpaceSm + 4),
                      const Text(
                        "Point at a friend's JAM code",
                        textAlign: TextAlign.center,
                        style: TextStyle(color: kTextSecondary, fontSize: 13),
                      ),
                      const SizedBox(height: kSpaceXl),
                      Center(
                        child: Text('OR ENTER CODE', style: kDuskTextTheme.labelSmall),
                      ),
                      const SizedBox(height: kSpaceMd),
                      AppTextField.code(
                        controller: _codeController,
                        onChanged: (val) => setState(() => _code = val.toUpperCase()),
                      ),
                      const SizedBox(height: kSpaceMd),
                      Center(
                        child: _selectedPlatform != null
                            ? PlatformBadge(
                                platform: _selectedPlatform == 'spotify'
                                    ? AppPlatform.spotify
                                    : AppPlatform.youtube,
                                label: _selectedPlatform == 'spotify'
                                    ? 'Joining via Spotify'
                                    : 'Joining via YouTube Music',
                                compact: true,
                              )
                            : NoPlatformConnectedBanner(
                                textAlign: TextAlign.center,
                                onConnect: () => context.push('/connect-platform'),
                              ),
                      ),
                      const SizedBox(height: kSpaceLg),
                      if (_error != null)
                        Padding(
                          padding: const EdgeInsets.only(bottom: kSpaceMd),
                          child: AppBanner(message: _error!, variant: AppBannerVariant.error),
                        ),
                      PrimaryButton(
                        label: 'Join',
                        onPressed: _code.length == 6 && !_isLoading && _selectedPlatform != null
                            ? _joinSession
                            : null,
                        isLoading: _isLoading,
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
// Scanner overlay — purple corner brackets + an animated scan-line glow
// (mockup image 6's viewfinder aesthetic). Screen-local: only used here.
// ---------------------------------------------------------------------------

class _ScannerOverlay extends StatefulWidget {
  const _ScannerOverlay();

  @override
  State<_ScannerOverlay> createState() => _ScannerOverlayState();
}

class _ScannerOverlayState extends State<_ScannerOverlay> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(seconds: 2))
      ..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) => CustomPaint(
          painter: _ScannerFramePainter(scanLineProgress: _controller.value),
          child: const SizedBox.expand(),
        ),
      ),
    );
  }
}

class _ScannerFramePainter extends CustomPainter {
  final double scanLineProgress;

  _ScannerFramePainter({required this.scanLineProgress});

  @override
  void paint(Canvas canvas, Size size) {
    final bracketLength = size.shortestSide * 0.12;
    final bracketPaint = Paint()
      ..color = kPrimary
      ..strokeWidth = 4
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    void drawCorner(Offset corner, Offset horizontal, Offset vertical) {
      canvas.drawLine(corner, corner + horizontal, bracketPaint);
      canvas.drawLine(corner, corner + vertical, bracketPaint);
    }

    drawCorner(const Offset(0, 0), Offset(bracketLength, 0), Offset(0, bracketLength));
    drawCorner(Offset(size.width, 0), Offset(-bracketLength, 0), Offset(0, bracketLength));
    drawCorner(Offset(0, size.height), Offset(bracketLength, 0), Offset(0, -bracketLength));
    drawCorner(
      Offset(size.width, size.height),
      Offset(-bracketLength, 0),
      Offset(0, -bracketLength),
    );

    final lineY = size.height * scanLineProgress;
    final linePaint = Paint()
      ..shader = LinearGradient(
        colors: [kPrimary.withAlpha(0), kPrimary, kPrimary.withAlpha(0)],
      ).createShader(Rect.fromLTWH(0, lineY - 1, size.width, 2));
    canvas.drawRect(Rect.fromLTWH(0, lineY - 1, size.width, 2), linePaint);
  }

  @override
  bool shouldRepaint(covariant _ScannerFramePainter oldDelegate) =>
      oldDelegate.scanLineProgress != scanLineProgress;
}
