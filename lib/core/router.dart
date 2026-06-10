import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/screens/login_screen.dart';
import '../features/auth/screens/register_screen.dart';
import '../features/auth/screens/connect_platform_screen.dart';
import '../features/home/screens/home_screen.dart';
import '../features/session/screens/create_session_screen.dart';
import '../features/session/screens/join_session_screen.dart';
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
  initialLocation: '/',
  routes: [
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
      path: '/home',
      pageBuilder: (context, state) => _slidePage(const HomeScreen()),
    ),
    GoRoute(
      path: '/session/create',
      pageBuilder: (context, state) => _slidePage(const CreateSessionScreen()),
    ),
    GoRoute(
      path: '/session/join',
      pageBuilder: (context, state) => _slidePage(const JoinSessionScreen()),
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
