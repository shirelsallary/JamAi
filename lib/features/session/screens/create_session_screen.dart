import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../../../core/auth_service.dart';
import '../../../core/constants.dart';
import '../../../core/theme.dart';

const _genres = ['Pop', 'Hip-Hop', 'Rock', 'Jazz', 'R&B', 'Latin', 'Electronic', 'Classical'];
const _moods = ['Energetic', 'Chill', 'Happy', 'Sad', 'Romantic', 'Focus'];
const _languages = ['English', 'Hebrew', 'Spanish', 'Arabic', 'French'];
const _times = ['Morning', 'Afternoon', 'Evening', 'Night', 'Late Night'];

class CreateSessionScreen extends StatefulWidget {
  const CreateSessionScreen({super.key});

  @override
  State<CreateSessionScreen> createState() => _CreateSessionScreenState();
}

class _CreateSessionScreenState extends State<CreateSessionScreen> {
  String? _selectedPlatform;
  String? _selectedGenre;
  String? _selectedMood;
  String? _selectedLanguage;
  String? _selectedTime;
  String? _customGenre;
  String? _customMood;
  String? _customLanguage;
  String? _customTime;
  bool _isLoading = false;

  bool get _canCreate => !_isLoading && _selectedPlatform != null;

  Future<void> _createSession() async {
    final token = await AuthService.getToken();
    if (token == null) {
      if (mounted) context.go('/');
      return;
    }

    setState(() => _isLoading = true);

    final genre = _customGenre ?? _selectedGenre;
    final mood = _customMood ?? _selectedMood;
    final language = _customLanguage ?? _selectedLanguage;
    final time = _customTime ?? _selectedTime;

    try {
      final response = await http.post(
        Uri.parse('$kBaseUrl/sessions'),
        headers: {
          'Authorization': 'Bearer $token',
          'Content-Type': 'application/json',
        },
        body: jsonEncode({
          'context_vector': {
            'genre': genre,
            'mood': mood,
            'language': language,
            'time': time,
          }
        }),
      );
      if (!mounted) return;

      if (response.statusCode == 201) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        if (_selectedPlatform != null) {
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('platform', _selectedPlatform!);
        }
        if (!mounted) return;
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
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // --- Platform selection ---
            const Text(
              'Choose your platform',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _PlatformButton(
                    label: 'Spotify',
                    color: kGreen,
                    isSelected: _selectedPlatform == 'spotify',
                    onTap: () => setState(() => _selectedPlatform = 'spotify'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _PlatformButton(
                    label: 'YouTube Music',
                    color: kRed,
                    isSelected: _selectedPlatform == 'youtube',
                    onTap: () => setState(() => _selectedPlatform = 'youtube'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 28),

            // --- Genre ---
            _TagSection(
              label: 'Genre',
              options: _genres,
              selected: _selectedGenre,
              onSelect: (v) => setState(() => _selectedGenre = v),
              customValue: _customGenre,
              onCustomChanged: (v) => setState(() => _customGenre = v),
            ),
            const SizedBox(height: 20),

            // --- Mood ---
            _TagSection(
              label: 'Mood',
              options: _moods,
              selected: _selectedMood,
              onSelect: (v) => setState(() => _selectedMood = v),
              customValue: _customMood,
              onCustomChanged: (v) => setState(() => _customMood = v),
            ),
            const SizedBox(height: 20),

            // --- Language ---
            _TagSection(
              label: 'Language',
              options: _languages,
              selected: _selectedLanguage,
              onSelect: (v) => setState(() => _selectedLanguage = v),
              customValue: _customLanguage,
              onCustomChanged: (v) => setState(() => _customLanguage = v),
            ),
            const SizedBox(height: 20),

            // --- Time ---
            _TagSection(
              label: 'Time of Day',
              options: _times,
              selected: _selectedTime,
              onSelect: (v) => setState(() => _selectedTime = v),
              customValue: _customTime,
              onCustomChanged: (v) => setState(() => _customTime = v),
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
            if (_selectedPlatform == null) ...[
              const SizedBox(height: 8),
              const Text(
                'Please select a platform to continue',
                style: TextStyle(color: kRed, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ],
            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Platform button
// ---------------------------------------------------------------------------

class _PlatformButton extends StatelessWidget {
  final String label;
  final Color color;
  final bool isSelected;
  final VoidCallback onTap;

  const _PlatformButton({
    required this.label,
    required this.color,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: isSelected ? color.withAlpha(30) : kSurface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isSelected ? color : Colors.grey.shade300,
            width: 2,
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 12,
              height: 12,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
            const SizedBox(width: 8),
            Text(
              label,
              style: TextStyle(
                fontWeight: FontWeight.bold,
                color: isSelected ? color : kTextSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Tag section (label + wrap of chips + custom "+" chip)
// ---------------------------------------------------------------------------

class _TagSection extends StatelessWidget {
  final String label;
  final List<String> options;
  final String? selected;
  final ValueChanged<String> onSelect;
  final String? customValue;
  final ValueChanged<String?> onCustomChanged;

  const _TagSection({
    required this.label,
    required this.options,
    required this.selected,
    required this.onSelect,
    required this.customValue,
    required this.onCustomChanged,
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
          children: [
            ...options.map((opt) => _TagChip(
                  label: opt,
                  isSelected: customValue == null && selected == opt,
                  onTap: () => onSelect(opt),
                )),
            _AddCustomChip(
              label: label,
              currentValue: customValue,
              onChanged: onCustomChanged,
            ),
          ],
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

// ---------------------------------------------------------------------------
// "+" custom chip with dialog
// ---------------------------------------------------------------------------

class _AddCustomChip extends StatefulWidget {
  final String label;
  final String? currentValue;
  final ValueChanged<String?> onChanged;

  const _AddCustomChip({
    required this.label,
    required this.currentValue,
    required this.onChanged,
  });

  @override
  State<_AddCustomChip> createState() => _AddCustomChipState();
}

class _AddCustomChipState extends State<_AddCustomChip> {
  Future<void> _openDialog() async {
    final controller = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Add custom ${widget.label.toLowerCase()}'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: 'e.g. Farewell party, Study session...',
          ),
          onSubmitted: (v) {
            if (v.trim().isNotEmpty) Navigator.of(ctx).pop(v.trim());
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              final v = controller.text.trim();
              if (v.isNotEmpty) Navigator.of(ctx).pop(v);
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );
    if (result != null) widget.onChanged(result);
  }

  @override
  Widget build(BuildContext context) {
    final hasValue = widget.currentValue != null;

    if (hasValue) {
      return GestureDetector(
        onTap: () => widget.onChanged(null),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            color: kCardAccent,
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: kPrimary),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                widget.currentValue!,
                style: const TextStyle(fontSize: 13, color: kPrimary),
              ),
              const SizedBox(width: 6),
              const Icon(Icons.close, size: 14, color: kPrimary),
            ],
          ),
        ),
      );
    }

    return GestureDetector(
      onTap: _openDialog,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: Colors.grey.shade400,
            strokeAlign: BorderSide.strokeAlignInside,
          ),
        ),
        child: const Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.add, size: 14, color: kTextSecondary),
            SizedBox(width: 4),
            Text(
              'Add your own...',
              style: TextStyle(fontSize: 13, color: kTextSecondary),
            ),
          ],
        ),
      ),
    );
  }
}
