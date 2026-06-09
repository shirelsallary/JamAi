import 'package:flutter/material.dart';

const Color kPrimary = Color(0xFF2979FF);
const Color kGreen = Color(0xFF1DB954);
const Color kRed = Color(0xFFFF4444);
const Color kBackground = Color(0xFFFFFFFF);
const Color kSurface = Color(0xFFF5F5F5);
const Color kCardAccent = Color(0xFFE8F0FF);
const Color kTextPrimary = Color(0xFF1A1A1A);
const Color kTextSecondary = Color(0xFF666666);

ThemeData jamAiTheme = ThemeData(
  primaryColor: kPrimary,
  scaffoldBackgroundColor: kBackground,
  colorScheme: const ColorScheme.light(primary: kPrimary),
  appBarTheme: const AppBarTheme(
    backgroundColor: kPrimary,
    foregroundColor: Colors.white,
    elevation: 0,
    centerTitle: true,
  ),
  elevatedButtonTheme: ElevatedButtonThemeData(
    style: ElevatedButton.styleFrom(
      backgroundColor: kPrimary,
      foregroundColor: Colors.white,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
      minimumSize: const Size(double.infinity, 48),
    ),
  ),
  cardTheme: CardThemeData(
    color: kBackground,
    elevation: 0,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(12),
      side: const BorderSide(color: Color(0xFFE0E0E0), width: 0.5),
    ),
  ),
  inputDecorationTheme: InputDecorationTheme(
    filled: true,
    fillColor: kSurface,
    border: OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: BorderSide.none,
    ),
    focusedBorder: OutlineInputBorder(
      borderRadius: BorderRadius.circular(12),
      borderSide: const BorderSide(color: kPrimary, width: 1.5),
    ),
  ),
);
