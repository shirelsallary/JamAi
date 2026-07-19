import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/screens/splash_screen.dart';
import '../features/auth/screens/login_screen.dart';
import '../features/auth/screens/register_screen.dart';
import '../features/auth/screens/connect_platform_screen.dart';
import '../features/auth/screens/youtube_webview_screen.dart';
import '../features/home/screens/home_screen.dart';
import '../features/session/screens/create_session_screen.dart';
import '../features/session/screens/join_session_screen.dart';
import '../features/session/screens/session_qr_screen.dart';
import '../features/session/screens/session_screen.dart';
import '../features/export/screens/export_screen.dart';

CustomTransitionPage<void> _slidePage(Widget child) {
  return CustomTransitionPage<void>(
    child: child,
    transitionsBuilder: (context, animation, secondary, child) {
      return SlideTransition(
        position: animation.drive(
          Tween(
            begin: const Offset(0.0, 0.08),
            end: Offset.zero,
          ).chain(CurveTween(curve: Curves.easeOutCubic)),
        ),
        child: FadeTransition(
          opacity: animation.drive(
            CurveTween(curve: Curves.easeOut),
          ),
          child: child,
        ),
      );
    },
    transitionDuration: const Duration(milliseconds: 300),
  );
}

final GoRouter appRouter = GoRouter(
  initialLocation: '/splash',
  routes: [
    GoRoute(
      path: '/splash',
      pageBuilder: (context, state) => _slidePage(const SplashScreen()),
    ),
    GoRoute(
      path: '/',
      pageBuilder: (context, state) => _slidePage(const LoginScreen()),
    ),
    GoRoute(
      path: '/register',
      pageBuilder: (context, state) => _slidePage(const RegisterScreen()),
    ),
    GoRoute(
      path: '/connect-platform',
      pageBuilder: (context, state) =>
          _slidePage(const ConnectPlatformScreen()),
    ),
    GoRoute(
      path: '/youtube-connect',
      pageBuilder: (context, state) =>
          _slidePage(const YouTubeWebViewScreen()),
    ),
    GoRoute(
      path: '/home',
      pageBuilder: (context, state) => _slidePage(const HomeScreen()),
    ),
    GoRoute(
      path: '/session/create',
      pageBuilder: (context, state) => _slidePage(const CreateSessionScreen()),
    ),
    GoRoute(
      path: '/session/:id/qr',
      // Reached only via go() from CreateSessionScreen's success handler,
      // passing session_code/qr_payload through `extra` (go_router's
      // mechanism for non-URL-encodable data) rather than query params —
      // qr_payload contains "://" which would need escaping as a query
      // string. Not part of the jamai:// deep-link scheme.
      pageBuilder: (context, state) {
        final extra = state.extra as Map<String, dynamic>?;
        return _slidePage(
          SessionQrScreen(
            sessionId: state.pathParameters['id']!,
            sessionCode: extra?['session_code'] as String? ?? '',
            qrPayload: extra?['qr_payload'] as String? ?? '',
          ),
        );
      },
    ),
    GoRoute(
      path: '/session/join',
      // ?code=... populated when reached via a jamai://join/{code} deep link.
      pageBuilder: (context, state) => _slidePage(
        JoinSessionScreen(initialCode: state.uri.queryParameters['code']),
      ),
    ),
    GoRoute(
      path: '/session/:id',
      pageBuilder: (context, state) => _slidePage(
        SessionScreen(sessionId: state.pathParameters['id']!),
      ),
    ),
    GoRoute(
      path: '/export/:id',
      pageBuilder: (context, state) => _slidePage(
        ExportScreen(sessionId: state.pathParameters['id']!),
      ),
    ),
  ],
);
