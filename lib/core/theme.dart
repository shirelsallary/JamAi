import 'package:flutter/material.dart';

// ---------------------------------------------------------------------------
// Dusk color tokens
// ---------------------------------------------------------------------------
//
// Names are kept stable from the pre-Dusk light theme wherever the ROLE is
// unchanged (background, surface, primary/secondary text, primary accent,
// Spotify green) — only the VALUE moves to fit the dark "dusk" palette, same
// as any theme redesign. Where the mockup introduces a genuinely NEW
// meaning that would otherwise collide with an existing token's established
// meaning (YouTube's brand red vs. the pre-existing kRed error/destructive
// red), a new token is added instead of repurposing the old one — see
// kYouTubeRed below.

/// Base background — near-black purple.
const Color kBackground = Color(0xFF160F19);

/// Solid filled-surface color (text input fill, disabled-button fill) — a
/// dark charcoal-purple a step lighter than [kBackground].
const Color kSurface = Color(0xFF231A29);

/// Translucent card fill. Composes as a light overlay over [kBackground]
/// (or the future dusk gradient background) so cards read as "slightly
/// lighter than background," not boxed — always paint this over
/// kBackground/the gradient, never over another opaque surface. Alpha
/// matches [kAlphaSubtle].
const Color kCardSurface = Color(0x14FFFFFF);

/// Accent-tinted card fill (e.g. now-playing / highlighted session cards) —
/// primary pink at [kAlphaSoft] over the card surface.
const Color kCardAccent = Color(0x28EC1876);

/// Upper-portion background radial glow — deep violet/indigo. Consumed by
/// the future GradientBackground shared widget, not by ThemeData directly
/// (Flutter's Scaffold/ThemeData can't express a background gradient).
const Color kGlowViolet = Color(0xFF4A2E86);

/// Lower-portion background radial glow — warm coral-orange.
const Color kGlowCoral = Color(0xFFFF6B4A);

/// Primary gradient (hot pink -> red), used for primary CTAs, the live dot,
/// avatars, and the Create JAM card fill. ThemeData/ElevatedButtonThemeData
/// cannot express a gradient fill, so this pair is meant to be consumed
/// directly by a custom PrimaryButton widget, not by elevatedButtonTheme.
const Color kPrimaryGradientStart = Color(0xFFEC1876);
const Color kPrimaryGradientEnd = Color(0xFFFF4D6D);
const List<Color> kPrimaryGradient = [kPrimaryGradientStart, kPrimaryGradientEnd];

/// Flat single-color primary accent (gradient's start color) — for contexts
/// that need one solid color rather than a gradient: colorScheme.primary,
/// focus borders, icon tints, "Score: X%"-style inline text.
const Color kPrimary = kPrimaryGradientStart;

/// Spotify brand green. Unchanged from the pre-Dusk theme — the mockup's
/// Spotify green matches this value already, so both the name and value
/// carry over as-is.
const Color kGreen = Color(0xFF1DB954);

/// Destructive/error red (End session, validation errors, failed states).
/// Same role and value as the pre-Dusk theme — kept distinct from YouTube's
/// brand red below even though both are "red".
const Color kRed = Color(0xFFFF4444);

/// YouTube Music brand red (selection dot/accent on platform-connect rows).
/// New token, not a repurposing of kRed — kRed's meaning stays
/// error/destructive; this is a separate, purely-branding red.
const Color kYouTubeRed = Color(0xFFFF0000);

/// Primary text — near-white, for headlines and high-emphasis body text.
const Color kTextPrimary = Color(0xFFF5F3F7);

/// Secondary/muted text — lavender-gray, for taglines, subtitles, captions,
/// and small-caps labels.
const Color kTextSecondary = Color(0xFF9B93A8);

// ---------------------------------------------------------------------------
// Alpha-tint scale
// ---------------------------------------------------------------------------
//
// Replaces the ad hoc withAlpha(20/30/50/80) values found scattered across
// screens pre-redesign, none of which mapped to a documented intent. Use
// `color.withAlpha(kAlphaX)` so every tint in the app maps to one of these
// four named levels.

/// Barely-there tint — glow bleed, background wash. ~8% opacity.
const int kAlphaSubtle = 20;

/// Soft fill — badge/banner backgrounds, chip fills, card accents. ~16%
/// opacity.
const int kAlphaSoft = 40;

/// Medium emphasis — glow borders, selected-state outlines. ~31% opacity.
const int kAlphaMedium = 80;

/// Strong emphasis — scrims, disabled overlays. ~51% opacity.
const int kAlphaStrong = 130;

// ---------------------------------------------------------------------------
// Spacing scale
// ---------------------------------------------------------------------------
//
// Replaces inline SizedBox/EdgeInsets magic numbers (8/12/16/24/28/32/48/60
// were all in use pre-redesign with no shared scale).

const double kSpaceXs = 4;
const double kSpaceSm = 8;
const double kSpaceMd = 16;
const double kSpaceLg = 24;
const double kSpaceXl = 32;
const double kSpaceXxl = 48;

// ---------------------------------------------------------------------------
// Radius scale
// ---------------------------------------------------------------------------
//
// The mockup uses large, consistent rounding everywhere — roughly 20-28px
// on cards/tiles, fully pill-shaped on every button/chip/input. Nothing in
// the redesign is sharp-cornered.

const double kRadiusSm = 12;
const double kRadiusMd = 20;
const double kRadiusLg = 28;

/// Fully pill-shaped — every primary/secondary button, chip, and text input
/// per the mockup. Deliberately larger than any real widget dimension so
/// BorderRadius.circular(kRadiusPill) always resolves to a stadium shape
/// regardless of height.
const double kRadiusPill = 999;

// ---------------------------------------------------------------------------
// Text theme
// ---------------------------------------------------------------------------
//
// The mockup calls for a bold "geometric grotesque" display font, distinct
// from the platform default. No font asset is bundled in this project today
// (no assets/fonts/, no `fonts:` entry in pubspec.yaml) — adding one is a
// separate decision (bundle a .ttf vs. depend on google_fonts), so this
// theme approximates the mockup's weight/scale using the platform default
// family at heavy weights (w700-w900) rather than silently pointing
// fontFamily at something that isn't in the bundle. Flagged as an open
// question in the Stage A report.

const TextTheme kDuskTextTheme = TextTheme(
  // Wordmark / largest display text (e.g. "JAM" on Login/Splash).
  displayLarge: TextStyle(
    fontSize: 40,
    fontWeight: FontWeight.w900,
    color: kTextPrimary,
    letterSpacing: -0.5,
  ),
  // Large screen headlines (e.g. "What are we vibing to?").
  headlineLarge: TextStyle(
    fontSize: 28,
    fontWeight: FontWeight.w800,
    color: kTextPrimary,
    height: 1.2,
  ),
  // Screen titles (e.g. "Connect your music", "Create a JAM").
  headlineMedium: TextStyle(
    fontSize: 22,
    fontWeight: FontWeight.w800,
    color: kTextPrimary,
  ),
  // Section/card/track titles.
  titleMedium: TextStyle(
    fontSize: 18,
    fontWeight: FontWeight.w700,
    color: kTextPrimary,
  ),
  // Default body text.
  bodyLarge: TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w400,
    color: kTextPrimary,
  ),
  // Muted/secondary body text (taglines, subtitles, artist names).
  bodyMedium: TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w400,
    color: kTextSecondary,
  ),
  // Small print (timestamps, fine detail).
  bodySmall: TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w400,
    color: kTextSecondary,
  ),
  // Small-caps-style labels (LIVE NOW, YOUR JAM IS LIVE, OR ENTER CODE) —
  // callers apply .toUpperCase() themselves; TextTheme can't enforce casing.
  labelSmall: TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w700,
    color: kTextSecondary,
    letterSpacing: 1.5,
  ),
);

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------

ThemeData jamAiTheme = ThemeData(
  brightness: Brightness.dark,
  primaryColor: kPrimary,
  scaffoldBackgroundColor: kBackground,
  colorScheme: const ColorScheme.dark(
    primary: kPrimary,
    secondary: kPrimaryGradientEnd,
    surface: kSurface,
    error: kRed,
  ),
  textTheme: kDuskTextTheme,
  appBarTheme: const AppBarTheme(
    // Mockup nav is minimal: a single back chevron, no app-bar background —
    // content sits directly on the gradient background (GradientBackground
    // widget, Part 2).
    backgroundColor: Colors.transparent,
    foregroundColor: kTextPrimary,
    elevation: 0,
    centerTitle: true,
  ),
  elevatedButtonTheme: ElevatedButtonThemeData(
    style: ElevatedButton.styleFrom(
      // Flat fallback fill for any ElevatedButton not routed through the
      // custom PrimaryButton (Part 2). Real primary CTAs use PrimaryButton
      // for the gradient-fill + glow treatment ThemeData can't express.
      backgroundColor: kPrimary,
      foregroundColor: Colors.white,
      disabledBackgroundColor: kSurface,
      disabledForegroundColor: kTextSecondary,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(kRadiusPill)),
      minimumSize: const Size(double.infinity, 48),
    ),
  ),
  outlinedButtonTheme: OutlinedButtonThemeData(
    style: OutlinedButton.styleFrom(
      // Previously missing entirely — every OutlinedButton (Home's "Join
      // JAM", Session's "End JAM") had to restate this inline per call site.
      foregroundColor: kTextPrimary,
      backgroundColor: kCardSurface,
      side: BorderSide(color: kTextSecondary.withAlpha(kAlphaMedium)),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(kRadiusPill)),
      minimumSize: const Size(double.infinity, 48),
    ),
  ),
  // No cardTheme: the previous cardTheme was defined but never actually
  // consumed by any screen (every "card" was a hand-rolled Container). The
  // mockup's cards are translucent, borderless surfaces that Material's
  // Card (elevation/shadow-based) doesn't model well, so this is replaced
  // by a custom AppCard widget in Part 2 rather than left as unused dead
  // config carried forward.
  inputDecorationTheme: InputDecorationTheme(
    filled: true,
    fillColor: kSurface,
    hintStyle: const TextStyle(color: kTextSecondary),
    labelStyle: const TextStyle(color: kTextSecondary),
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(kRadiusPill),
      borderSide: BorderSide.none,
    ),
    enabledBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(kRadiusPill),
      borderSide: BorderSide.none,
    ),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(kRadiusPill),
      borderSide: const BorderSide(color: kPrimary, width: 1.5),
    ),
  ),
);
