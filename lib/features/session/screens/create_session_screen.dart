import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';
import '../../../core/widgets/widgets.dart';

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
        // Stage E: insert the "Your JAM is live" QR-display screen between
        // creation and the live session — go() (not push), same reasoning
        // as before: the session already exists server-side, so there's no
        // safe "back" destination to a form that would resubmit.
        context.go(
          '/session/${data['id']}/qr',
          extra: {
            'session_code': data['session_code'],
            'qr_payload': data['qr_payload'],
          },
        );
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
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Create JAM'),
        leading: Navigator.canPop(context)
            ? AppBackButton(onPressed: () => context.pop())
            : null,
      ),
      body: GradientBackground(
        child: SafeArea(
          child: _loadingPlatform
              ? const Center(child: CircularProgressIndicator(color: kPrimary))
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(kSpaceMd),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // --- Platform (auto-selected, read-only display) ---
                      // NOTE: the mockup depicts this as a two-row toggle
                      // (Spotify selected / YouTube unselected), but that
                      // doesn't reflect this screen's actual behavior — the
                      // host's platform is auto-selected and not
                      // user-choosable (at most one platform is connected
                      // per account today; see the pre-existing comment on
                      // _hostPlatform below). Kept as the single
                      // read-only badge/banner it already was, restyled,
                      // rather than building a two-option toggle UI that
                      // would imply a choice the app doesn't support.
                      Text('Playing via', style: kDuskTextTheme.titleMedium),
                      const SizedBox(height: kSpaceSm + 4),
                      if (_hostPlatform != null)
                        PlatformBadge(
                          platform: _hostPlatform == 'spotify'
                              ? AppPlatform.spotify
                              : AppPlatform.youtube,
                        )
                      else
                        NoPlatformConnectedBanner(
                          onConnect: () => context.push('/connect-platform'),
                        ),
                      const SizedBox(height: kSpaceXl + 4),

                      // --- Duration ---
                      Text('Target duration', style: kDuskTextTheme.titleMedium),
                      const SizedBox(height: kSpaceSm + 4),
                      Wrap(
                        spacing: kSpaceSm,
                        children: _durations
                            .map((d) => TagChip(
                                  label: '$d min',
                                  isSelected: _selectedDuration == d,
                                  onTap: () => setState(() => _selectedDuration = d),
                                ))
                            .toList(),
                      ),
                      const SizedBox(height: kSpaceXl + 4),

                      // --- Genre ---
                      TagSection(
                        label: 'Genre',
                        options: _genres,
                        selected: _selectedGenre,
                        onSelect: (v) => setState(
                          () => _selectedGenre = _selectedGenre == v ? null : v,
                        ),
                      ),
                      const SizedBox(height: kSpaceLg - 4),

                      // --- Mood ---
                      TagSection(
                        label: 'Mood',
                        options: _moods,
                        selected: _selectedMood,
                        onSelect: (v) => setState(
                          () => _selectedMood = _selectedMood == v ? null : v,
                        ),
                      ),
                      const SizedBox(height: kSpaceLg - 4),

                      // --- Language ---
                      TagSection(
                        label: 'Language',
                        options: _languages,
                        selected: _selectedLanguage,
                        onSelect: (v) => setState(
                          () => _selectedLanguage = _selectedLanguage == v ? null : v,
                        ),
                      ),
                      const SizedBox(height: kSpaceLg - 4),

                      // --- Time ---
                      TagSection(
                        label: 'Time of Day',
                        options: _times,
                        selected: _selectedTime,
                        onSelect: (v) => setState(
                          () => _selectedTime = _selectedTime == v ? null : v,
                        ),
                      ),
                      const SizedBox(height: kSpaceXl),

                      // --- Create button ---
                      PrimaryButton(
                        label: 'Create JAM Session',
                        onPressed: _canCreate ? _createSession : null,
                        isLoading: _isLoading,
                      ),
                      const SizedBox(height: kSpaceLg),
                    ],
                  ),
                ),
        ),
      ),
    );
  }
}
