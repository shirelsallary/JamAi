import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<Map<String, dynamic>> _sessions = [];
  bool _loading = true;
  int _currentIndex = 0;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    final token = await AuthService.getToken();
    if (token == null) {
      if (mounted) context.go('/');
      return;
    }

    try {
      final response = await http.get(
        Uri.parse('$kBaseUrl/users/me/history'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (!mounted) return;

      if (response.statusCode == 200) {
        final List<dynamic> data = jsonDecode(response.body);
        setState(() {
          _sessions = data.cast<Map<String, dynamic>>();
        });
      }
    } catch (_) {
      // history is non-critical — show empty list on failure
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _logout() async {
    await AuthService.logout();
    if (mounted) context.go('/');
  }

  @override
  Widget build(BuildContext context) {
    // Same _sessions data as before, just grouped for display by the
    // status field already present on every session — no new fetching or
    // filtering criteria beyond what was already available.
    final liveSessions = _sessions.where((s) => s['status'] == 'active').toList();
    final pastSessions = _sessions.where((s) => s['status'] != 'active').toList();

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        // Kept as "JAM AI" (not the mockup's shorter "JAM") — same
        // established decision as the auth screens' wordmark.
        title: const Text('JAM AI'),
        actions: [
          IconButton(
            key: const Key('manage-spotify-connection-button'),
            icon: const Icon(Icons.music_note_outlined),
            tooltip: 'Manage Spotify Connection',
            // push (not go), and unconditional — ConnectPlatformScreen is
            // otherwise only reachable via routes that skip it once
            // platform_token is non-empty (login/register/splash), so an
            // already-connected user has no way back in to re-grant newly
            // added scopes without this entry point.
            onPressed: () => context.push('/connect-platform'),
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Logout',
            onPressed: _logout,
          ),
          const Padding(
            padding: EdgeInsets.only(right: kSpaceMd),
            child: Avatar(size: 36),
          ),
        ],
      ),
      body: GradientBackground(
        child: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(kSpaceMd, kSpaceSm, kSpaceMd, kSpaceMd),
                child: Text(
                  'What are we vibing to?',
                  style: kDuskTextTheme.headlineLarge,
                ),
              ),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: kSpaceMd),
                child: Row(
                  children: [
                    Expanded(
                      child: _HomeActionCard(
                        icon: Icons.add,
                        label: 'Create JAM',
                        isPrimary: true,
                        // push — user should be able to back out of the
                        // create form to Home (see navigation audit).
                        onTap: () => context.push('/session/create'),
                      ),
                    ),
                    const SizedBox(width: kSpaceMd),
                    Expanded(
                      child: _HomeActionCard(
                        icon: Icons.qr_code_scanner,
                        label: 'Join JAM',
                        isPrimary: false,
                        onTap: () => context.push('/session/join'),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: kSpaceLg),
              Expanded(
                child: _loading
                    ? const Center(child: CircularProgressIndicator(color: kPrimary))
                    : RefreshIndicator(
                        color: kPrimary,
                        onRefresh: _loadHistory,
                        child: _sessions.isEmpty
                            ? ListView(
                                physics: const AlwaysScrollableScrollPhysics(),
                                children: const [
                                  SizedBox(height: 120),
                                  Center(
                                    child: Text(
                                      'No sessions yet',
                                      style: TextStyle(color: kTextSecondary),
                                    ),
                                  ),
                                ],
                              )
                            : ListView(
                                padding: const EdgeInsets.symmetric(horizontal: kSpaceMd),
                                children: [
                                  if (liveSessions.isNotEmpty) ...[
                                    Row(
                                      children: [
                                        Container(
                                          width: 8,
                                          height: 8,
                                          decoration: const BoxDecoration(
                                            color: kPrimary,
                                            shape: BoxShape.circle,
                                          ),
                                        ),
                                        const SizedBox(width: kSpaceSm),
                                        Text(
                                          'LIVE NOW',
                                          style: kDuskTextTheme.labelSmall
                                              ?.copyWith(color: kPrimary),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: kSpaceSm),
                                    ...liveSessions.map((s) => _SessionCard(session: s)),
                                    const SizedBox(height: kSpaceLg),
                                  ],
                                  if (pastSessions.isNotEmpty) ...[
                                    Text('Past Sessions', style: kDuskTextTheme.titleMedium),
                                    const SizedBox(height: kSpaceSm),
                                    ...pastSessions.map((s) => _SessionCard(session: s)),
                                  ],
                                ],
                              ),
                      ),
              ),
            ],
          ),
        ),
      ),
      bottomNavigationBar: BottomNavigationBar(
        backgroundColor: kSurface,
        currentIndex: _currentIndex,
        selectedItemColor: kPrimary,
        unselectedItemColor: kTextSecondary,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.home),
            label: 'Home',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.add_circle_outline),
            label: 'Create JAM',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.qr_code_scanner),
            label: 'Join JAM',
          ),
        ],
        onTap: (index) {
          if (index == 0) setState(() => _currentIndex = 0);
          if (index == 1) context.push('/session/create');
          if (index == 2) context.push('/session/join');
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Home action card — the mockup's square "Create JAM"/"Join JAM" tiles.
// Screen-local (like ConnectPlatformScreen's _PlatformConnectButton): only
// used here, so not promoted to the shared widget library.
// ---------------------------------------------------------------------------

class _HomeActionCard extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool isPrimary;
  final VoidCallback onTap;

  const _HomeActionCard({
    required this.icon,
    required this.label,
    required this.isPrimary,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AspectRatio(
        aspectRatio: 1,
        child: Container(
          padding: const EdgeInsets.all(kSpaceMd),
          decoration: BoxDecoration(
            gradient: isPrimary ? const LinearGradient(colors: kPrimaryGradient) : null,
            color: isPrimary ? null : kCardSurface,
            borderRadius: BorderRadius.circular(kRadiusMd),
            boxShadow: isPrimary
                ? [
                    BoxShadow(
                      color: kPrimaryGradientStart.withAlpha(kAlphaMedium),
                      blurRadius: 20,
                      offset: const Offset(0, 8),
                    ),
                  ]
                : null,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Icon(icon, color: isPrimary ? Colors.white : kTextPrimary, size: 28),
              Text(
                label,
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: isPrimary ? Colors.white : kTextPrimary,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SessionCard extends StatelessWidget {
  final Map<String, dynamic> session;

  const _SessionCard({required this.session});

  @override
  Widget build(BuildContext context) {
    final code = session['session_code'] ?? '—';
    final status = session['status'] ?? 'closed';
    final isActive = status == 'active';
    final contextVector =
        session['context_vector'] as Map<String, dynamic>? ?? {};
    final genre = contextVector['genre'] ?? '';
    final mood = contextVector['mood'] ?? '';
    final subtitle = [genre, mood].where((s) => s.isNotEmpty).join(' · ');

    return GestureDetector(
      // push — drilling into a past/active session from the history list
      // should be back-able to Home, unlike landing there right after
      // creating/joining (see navigation audit).
      onTap: () => context.push('/session/${session['id']}'),
      child: Container(
        margin: const EdgeInsets.only(bottom: kSpaceSm + 2),
        padding: const EdgeInsets.symmetric(horizontal: kSpaceMd, vertical: kSpaceSm + 2),
        decoration: BoxDecoration(
          color: isActive ? kCardAccent : kCardSurface,
          borderRadius: BorderRadius.circular(kRadiusMd),
          border: isActive ? Border.all(color: kPrimary.withAlpha(kAlphaMedium)) : null,
        ),
        child: Row(
          children: [
            Icon(
              isActive ? Icons.graphic_eq : Icons.check_circle_outline,
              color: isActive ? kPrimary : kTextSecondary,
              size: 20,
            ),
            const SizedBox(width: kSpaceSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    code,
                    style: const TextStyle(fontWeight: FontWeight.bold, color: kTextPrimary),
                  ),
                  if (subtitle.isNotEmpty)
                    Text(subtitle, style: const TextStyle(color: kTextSecondary, fontSize: 12)),
                ],
              ),
            ),
            if (!isActive) Text('ENDED', style: kDuskTextTheme.labelSmall),
          ],
        ),
      ),
    );
  }
}
