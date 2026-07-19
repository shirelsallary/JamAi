import 'package:flutter/material.dart';
import '../theme.dart';

/// Pill-shaped dark text field matching the Dusk input treatment. A thin
/// wrapper over [TextField] exposing only the subset of parameters screens
/// actually use today (controller, label/hint/helper text, obscureText,
/// keyboard type, capitalization, alignment, change/submit callbacks) —
/// visual styling (fill, pill radius, focus border) comes from
/// [jamAiTheme]'s inputDecorationTheme, not from anything set here.
class AppTextField extends StatelessWidget {
  final TextEditingController? controller;
  final String? labelText;
  final String? hintText;
  final String? helperText;
  final bool obscureText;
  final TextInputType? keyboardType;
  final TextCapitalization textCapitalization;
  final TextAlign textAlign;
  final TextStyle? style;
  final int? maxLength;
  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;

  /// Explicit overrides for suggestion/autocorrect behavior. Default to
  /// `!obscureText` when omitted (a password field disables both, a normal
  /// field allows both) — but some fields need both off regardless of
  /// obscureText (e.g. an email field, where autocorrect actively mangles
  /// addresses). Added for LoginScreen/RegisterScreen's email fields, which
  /// forced both off explicitly before this widget existed.
  final bool? enableSuggestions;
  final bool? autocorrect;

  const AppTextField({
    super.key,
    this.controller,
    this.labelText,
    this.hintText,
    this.helperText,
    this.obscureText = false,
    this.keyboardType,
    this.textCapitalization = TextCapitalization.none,
    this.textAlign = TextAlign.start,
    this.style,
    this.maxLength,
    this.onChanged,
    this.onSubmitted,
    this.enableSuggestions,
    this.autocorrect,
  });

  /// The large, centered, letter-spaced 6-character session-code field
  /// (JoinSessionScreen's code entry). Preset values are copied verbatim
  /// from the current inline TextField in join_session_screen.dart (fontSize
  /// 28, bold, letterSpacing 8, centered, uppercase-on-input, maxLength 6,
  /// hint 'XXXXXX') so Stage E can drop this in without re-deriving the
  /// look. Session codes stay 6-digit per the confirmed scope decision —
  /// this is NOT the mockup's 4-char `#K7QX` style.
  factory AppTextField.code({
    Key? key,
    TextEditingController? controller,
    String hintText = 'XXXXXX',
    ValueChanged<String>? onChanged,
    ValueChanged<String>? onSubmitted,
  }) {
    return AppTextField(
      key: key,
      controller: controller,
      hintText: hintText,
      maxLength: 6,
      textAlign: TextAlign.center,
      textCapitalization: TextCapitalization.characters,
      style: const TextStyle(
        fontSize: 28,
        fontWeight: FontWeight.bold,
        letterSpacing: 8,
        color: kTextPrimary,
      ),
      onChanged: onChanged,
      onSubmitted: onSubmitted,
    );
  }

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      obscureText: obscureText,
      keyboardType: keyboardType,
      textCapitalization: textCapitalization,
      textAlign: textAlign,
      enableSuggestions: enableSuggestions ?? !obscureText,
      autocorrect: autocorrect ?? !obscureText,
      maxLength: maxLength,
      style: style ?? const TextStyle(color: kTextPrimary),
      onChanged: onChanged,
      onSubmitted: onSubmitted,
      decoration: InputDecoration(
        labelText: labelText,
        hintText: hintText,
        helperText: helperText,
        counterText: maxLength != null ? '' : null,
      ),
    );
  }
}
