import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:qr_flutter/qr_flutter.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

/// "Your JAM is live" QR-display screen (mockup image 5) — shown once,
/// between session creation and the live session view, so the host can
/// share the session before diving into the queue.
///
/// [qrPayload] is rendered exactly as returned by the backend
/// (`POST /sessions`'s `qr_payload` field — currently `jamai://join/{code}`)
/// — this screen does not invent its own QR content format. Scanning it
/// with any reader (the in-app scanner added this same stage, or the OS's
/// existing `jamai://` intent-filter) resolves through the exact same
/// pre-existing deep-link path, untouched by this screen.
class SessionQrScreen extends StatelessWidget {
  final String sessionId;
  final String sessionCode;
  final String qrPayload;

  const SessionQrScreen({
    super.key,
    required this.sessionId,
    required this.sessionCode,
    required this.qrPayload,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        // No pop() available — this screen is reached via go() (a stack
        // reset) from CreateSessionScreen, matching the existing convention
        // of not letting a completed create-session flow back into the form
        // (see home_screen.dart's _SessionCard comment on the same pattern).
        // Mirrors SessionScreen's own back-icon treatment: an explicit
        // navigation, not a pop, since Navigator.canPop would be false here.
        leading: AppBackButton(onPressed: () => context.go('/home')),
      ),
      body: GradientBackground(
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(kSpaceLg),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Center(
                  child: Text(
                    'YOUR JAM IS LIVE',
                    style: kDuskTextTheme.labelSmall?.copyWith(color: kPrimary),
                  ),
                ),
                const SizedBox(height: kSpaceSm),
                Center(
                  child: Text(
                    // Real codes are 6-char alphanumeric (see
                    // AuthService/session_service.py), not the mockup's
                    // 4-char "#K7QX" — shown bare, no "#" prefix, matching
                    // how the code appears everywhere else in this app
                    // (HomeScreen's session cards, the manual entry field).
                    sessionCode.isNotEmpty ? sessionCode : '——————',
                    style: kDuskTextTheme.displayLarge,
                  ),
                ),
                const SizedBox(height: kSpaceXl),
                Center(
                  child: Container(
                    padding: const EdgeInsets.all(kSpaceLg),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(kRadiusLg),
                    ),
                    child: qrPayload.isNotEmpty
                        ? QrImageView(
                            data: qrPayload,
                            size: 220,
                            backgroundColor: Colors.white,
                          )
                        : const SizedBox(
                            width: 220,
                            height: 220,
                            child: Center(
                              child: Icon(Icons.qr_code_2, size: 64, color: kTextSecondary),
                            ),
                          ),
                  ),
                ),
                const SizedBox(height: kSpaceLg),
                const Text(
                  'Friends scan this to join your shared queue — no app needed.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: kTextSecondary, fontSize: 14),
                ),
                const SizedBox(height: kSpaceXl),
                PrimaryButton(
                  label: 'Start jamming',
                  onPressed: () => context.go('/session/$sessionId'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
