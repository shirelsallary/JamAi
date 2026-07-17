import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';

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
    return Scaffold(
      backgroundColor: kBackground,
      appBar: AppBar(
        title: const Text('JAM AI'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Logout',
            onPressed: _logout,
          ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: ElevatedButton.icon(
                    icon: const Icon(Icons.add),
                    label: const Text('Create JAM'),
                    // push — user should be able to back out of the create
                    // form to Home (see navigation audit).
                    onPressed: () => context.push('/session/create'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton.icon(
                    icon: const Icon(Icons.qr_code_scanner),
                    label: const Text('Join JAM'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: kPrimary,
                      side: const BorderSide(color: kPrimary),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(24),
                      ),
                      minimumSize: const Size(double.infinity, 48),
                    ),
                    onPressed: () => context.push('/session/join'),
                  ),
                ),
              ],
            ),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Text(
              'Past Sessions',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
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
                        : ListView.builder(
                            padding: const EdgeInsets.symmetric(horizontal: 16),
                            itemCount: _sessions.length,
                            itemBuilder: (ctx, i) =>
                                _SessionCard(session: _sessions[i]),
                          ),
                  ),
          ),
        ],
      ),
      bottomNavigationBar: BottomNavigationBar(
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

class _SessionCard extends StatelessWidget {
  final Map<String, dynamic> session;

  const _SessionCard({required this.session});

  @override
  Widget build(BuildContext context) {
    final code = session['session_code'] ?? '—';
    final status = session['status'] ?? 'closed';
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
        margin: const EdgeInsets.only(bottom: 10),
        decoration: BoxDecoration(
          color: kCardAccent,
          borderRadius: BorderRadius.circular(12),
          border: const Border(
            left: BorderSide(color: kPrimary, width: 4),
          ),
        ),
        child: ListTile(
          title: Text(
            code,
            style: const TextStyle(
              fontWeight: FontWeight.bold,
              color: kTextPrimary,
            ),
          ),
          subtitle: subtitle.isNotEmpty
              ? Text(subtitle, style: const TextStyle(color: kTextSecondary))
              : null,
          trailing: _StatusChip(status: status),
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  final String status;

  const _StatusChip({required this.status});

  @override
  Widget build(BuildContext context) {
    final isActive = status == 'active';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: isActive ? kGreen.withAlpha(30) : Colors.grey.shade100,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        status,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          color: isActive ? kGreen : kTextSecondary,
        ),
      ),
    );
  }
}
