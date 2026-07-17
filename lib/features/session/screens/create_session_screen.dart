import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';

const _genres = ['Pop', 'Hip-Hop', 'Rock', 'Jazz', 'R&B', 'Latin', 'Electronic', 'Classical'];
const _moods = ['Energetic', 'Chill', 'Happy', 'Sad', 'Romantic', 'Focus'];
const _languages = ['English', 'Hebrew', 'Spanish', 'Arabic', 'French'];
const _times = ['Morning', 'Afternoon', 'Evening', 'Night', 'Late Night'];
const _durations = [30, 60, 90, 120];

class CreateSessionScreen extends StatefulWidget {
  const CreateSessionScreen({super.key});

  @override
  State<CreateSessionScreen> createState() => _CreateSessionScreenState();
}

class _CreateSessionScreenState extends State<CreateSessionScreen> {
  String? _selectedGenre;
  String? _selectedMood;
  String? _selectedLanguage;
  String? _selectedTime;
  int _selectedDuration = 60;
  bool _isLoading = false;

  // Section 0 — the host's own connected platform, auto-selected (single
  // platform per account today; see project notes). Not user-choosable here
  // because there is at most one to choose from.
  bool _loadingPlatform = true;
  String? _hostPlatform;

  bool get _canCreate => !_isLoading && _hostPlatform != null;

  @override
  void initState() {
    super.initState();
    _loadHostPlatform();
  }

  Future<void> _loadHostPlatform() async {
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
      _hostPlatform = (platform != null && platformToken != null && platformToken.isNotEmpty)
          ? platform
          : null;
      _loadingPlatform = false;
    });
  }

  Future<void> _createSession() async {
    final token = await AuthService.getToken();
    if (token == null) {
      if (mounted) context.go('/');
      return;
    }
    if (_hostPlatform == null) return;

    setState(() => _isLoading = true);

    try {
      final response = await http.post(
        Uri.parse('$kBaseUrl/sessions'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'context_vector': {
            'genre': _selectedGenre,
            'mood': _selectedMood,
            'language': _selectedLanguage,
            'time': _selectedTime,
          },
          'host_platform': _hostPlatform,
          'target_duration_minutes': _selectedDuration,
        }),
      );
      if (!mounted) return;

      if (response.statusCode == 201) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        context.go('/session/${data['id']}');
      } else {
        _showError('Failed to create session. Please try again.');
      }
    } catch (_) {
      if (mounted) _showError('Connection failed. Please try again.');
    } finally {
      if (mounted) setState(() => _isLoading = false);
    }
  }

  void _showError(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: kRed),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: kBackground,
      appBar: AppBar(
        title: const Text('Create JAM'),
        leading: Navigator.canPop(context)
            ? IconButton(
                icon: const Icon(Icons.arrow_back_ios, color: Colors.white),
                onPressed: () => context.pop(),
              )
            : null,
      ),
      body: _loadingPlatform
          ? const Center(child: CircularProgressIndicator(color: kPrimary))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // --- Platform (auto-selected, read-only display) ---
                  const Text(
                    'Playing via',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 12),
                  if (_hostPlatform != null)
                    _PlatformBadge(platform: _hostPlatform!)
                  else
                    _NoPlatformConnectedBanner(
                      onConnect: () => context.push('/connect-platform'),
                    ),
                  const SizedBox(height: 28),

                  // --- Duration ---
                  const Text(
                    'Target duration',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    children: _durations
                        .map((d) => _TagChip(
                              label: '$d min',
                              isSelected: _selectedDuration == d,
                              onTap: () => setState(() => _selectedDuration = d),
                            ))
                        .toList(),
                  ),
                  const SizedBox(height: 28),

                  // --- Genre ---
                  _TagSection(
                    label: 'Genre',
                    options: _genres,
                    selected: _selectedGenre,
                    onSelect: (v) => setState(
                      () => _selectedGenre = _selectedGenre == v ? null : v,
                    ),
                  ),
                  const SizedBox(height: 20),

                  // --- Mood ---
                  _TagSection(
                    label: 'Mood',
                    options: _moods,
                    selected: _selectedMood,
                    onSelect: (v) => setState(
                      () => _selectedMood = _selectedMood == v ? null : v,
                    ),
                  ),
                  const SizedBox(height: 20),

                  // --- Language ---
                  _TagSection(
                    label: 'Language',
                    options: _languages,
                    selected: _selectedLanguage,
                    onSelect: (v) => setState(
                      () => _selectedLanguage = _selectedLanguage == v ? null : v,
                    ),
                  ),
                  const SizedBox(height: 20),

                  // --- Time ---
                  _TagSection(
                    label: 'Time of Day',
                    options: _times,
                    selected: _selectedTime,
                    onSelect: (v) => setState(
                      () => _selectedTime = _selectedTime == v ? null : v,
                    ),
                  ),
                  const SizedBox(height: 32),

                  // --- Create button ---
                  ElevatedButton(
                    onPressed: _canCreate ? _createSession : null,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: _canCreate ? kPrimary : Colors.grey.shade300,
                      foregroundColor: _canCreate ? Colors.white : kTextSecondary,
                      minimumSize: const Size(double.infinity, 48),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(24),
                      ),
                    ),
                    child: _isLoading
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          )
                        : const Text('Create JAM Session'),
                  ),
                  const SizedBox(height: 24),
                ],
              ),
            ),
    );
  }
}

// ---------------------------------------------------------------------------
// Platform badge / no-platform banner
// ---------------------------------------------------------------------------

class _PlatformBadge extends StatelessWidget {
  final String platform;

  const _PlatformBadge({required this.platform});

  @override
  Widget build(BuildContext context) {
    final isSpotify = platform == 'spotify';
    final color = isSpotify ? kGreen : kRed;
    final label = isSpotify ? 'Spotify' : 'YouTube Music';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color.withAlpha(20),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color, width: 1.5),
      ),
      child: Row(
        children: [
          Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 8),
          Text(label, style: TextStyle(fontWeight: FontWeight.bold, color: color)),
        ],
      ),
    );
  }
}

class _NoPlatformConnectedBanner extends StatelessWidget {
  final VoidCallback onConnect;

  const _NoPlatformConnectedBanner({required this.onConnect});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: kRed.withAlpha(20),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: kRed, width: 1.5),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            "You haven't connected a platform yet.",
            style: TextStyle(color: kRed, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: onConnect,
            child: const Text('Connect Spotify or YouTube Music'),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Tag section (label + wrap of chips) — no custom "+" entry (removed: DNA
// scoring only supports the fixed genre/mood/time maps, see project notes).
// ---------------------------------------------------------------------------

class _TagSection extends StatelessWidget {
  final String label;
  final List<String> options;
  final String? selected;
  final ValueChanged<String> onSelect;

  const _TagSection({
    required this.label,
    required this.options,
    required this.selected,
    required this.onSelect,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: options
              .map((opt) => _TagChip(
                    label: opt,
                    isSelected: selected == opt,
                    onTap: () => onSelect(opt),
                  ))
              .toList(),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Tag chip
// ---------------------------------------------------------------------------

class _TagChip extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const _TagChip({
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? kCardAccent : kSurface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: isSelected ? kPrimary : Colors.transparent,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13,
            color: isSelected ? kPrimary : kTextSecondary,
          ),
        ),
      ),
    );
  }
}
