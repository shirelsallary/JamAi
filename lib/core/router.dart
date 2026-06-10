import 'package:go_router/go_router.dart';

import '../features/auth/screens/login_screen.dart';
import '../features/auth/screens/register_screen.dart';
import '../features/home/screens/home_screen.dart';
import '../features/session/screens/create_session_screen.dart';
import '../features/session/screens/join_session_screen.dart';
import '../features/session/screens/session_screen.dart';
import '../features/export/screens/export_screen.dart';

final GoRouter appRouter = GoRouter(
  initialLocation: '/',
  routes: [
    GoRoute(
      path: '/',
      builder: (context, state) => const LoginScreen(),
    ),
    GoRoute(
      path: '/register',
      builder: (context, state) => const RegisterScreen(),
    ),
    GoRoute(
      path: '/home',
      builder: (context, state) => const HomeScreen(),
    ),
    GoRoute(
      path: '/session/create',
      builder: (context, state) => const CreateSessionScreen(),
    ),
    GoRoute(
      path: '/session/join',
      builder: (context, state) => const JoinSessionScreen(),
    ),
    GoRoute(
      path: '/session/:id',
      builder: (context, state) => SessionScreen(
        sessionId: state.pathParameters['id']!,
      ),
    ),
    GoRoute(
      path: '/export/:id',
      builder: (context, state) => ExportScreen(
        sessionId: state.pathParameters['id']!,
      ),
    ),
  ],
);
