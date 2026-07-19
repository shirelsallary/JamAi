import 'package:flutter/material.dart';
import '../theme.dart';

/// A single selectable pill chip. Relocated out of create_session_screen.dart
/// (previously private `_TagChip`) and generalized for reuse — it was
/// already well-factored per the audit, so this is a move, not a rewrite.
class TagChip extends StatelessWidget {
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  const TagChip({
    super.key,
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: kSpaceMd, vertical: kSpaceSm),
        decoration: BoxDecoration(
          color: isSelected ? kCardAccent : kSurface,
          borderRadius: BorderRadius.circular(kRadiusPill),
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

/// A labeled section of wrapping [TagChip]s. Relocated out of
/// create_session_screen.dart (previously private `_TagSection`).
class TagSection extends StatelessWidget {
  final String label;
  final List<String> options;
  final String? selected;
  final ValueChanged<String> onSelect;

  const TagSection({
    super.key,
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
          style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: kTextPrimary),
        ),
        const SizedBox(height: kSpaceSm),
        Wrap(
          spacing: kSpaceSm,
          runSpacing: kSpaceSm,
          children: options
              .map((opt) => TagChip(
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
