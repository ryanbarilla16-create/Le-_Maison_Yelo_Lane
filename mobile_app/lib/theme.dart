import 'package:flutter/material.dart';

// ═══ APP COLORS (matching web CSS variables) ═══
class AppColors {
  static const Color primary = Color(0xFF8B634B); // --admin-accent
  static const Color primaryLight = Color(0xFFA0522D); // --admin-yellow
  static const Color accent = Color(0xFFD4A862);
  static const Color background = Color(0xFFFDFBF9); // --admin-bg (top)
  static const Color cardBg = Color(0xFFF8F1EB); // --admin-surface
  static const Color textMain = Color(0xFF4A3B32); // --admin-text
  static const Color textMuted = Color(0xFF8B634B); // --admin-text-muted
  static const Color success = Color(0xFF5C3A21); // --admin-green
  static const Color warning = Color(0xFFA0522D); // --admin-yellow
  static const Color danger = Color(0xFF8B634B); // --admin-red
  static const Color info = Color(0xFF8B634B); // --admin-blue
  static const Color gold = Color(0xFFA0522D);
}

// ═══ APP TEXT STYLES ═══
class AppTextStyles {
  static const TextStyle heading = TextStyle(
    fontFamily: 'Georgia',
    fontWeight: FontWeight.bold,
    color: AppColors.textMain,
  );

  static const TextStyle body = TextStyle(
    fontSize: 14,
    color: AppColors.textMain,
  );

  static const TextStyle muted = TextStyle(
    fontSize: 13,
    color: AppColors.textMuted,
  );

  static const TextStyle label = TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w600,
    color: AppColors.textMuted,
    letterSpacing: 1.5,
  );
}

// ═══ APP THEME ═══
ThemeData appTheme() {
  return ThemeData(
    fontFamily: 'Inter',
    scaffoldBackgroundColor: AppColors.background,
    primaryColor: AppColors.primary,
    colorScheme: ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      primary: AppColors.primary,
      secondary: AppColors.accent,
      surface: AppColors.cardBg, // using the chill latte background
      background: AppColors.background,
    ),
    appBarTheme: const AppBarTheme(
      backgroundColor: Colors.transparent, // transparent for chill vibe
      elevation: 0,
      centerTitle: true,
      iconTheme: IconThemeData(color: AppColors.textMain),
      titleTextStyle: TextStyle(
        fontFamily: 'Georgia',
        fontWeight: FontWeight.bold,
        fontSize: 20,
        color: AppColors.textMain,
      ),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)), // smoother round buttons
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16), // slightly taller
        textStyle: const TextStyle(fontWeight: FontWeight.w600, fontSize: 15),
        elevation: 2,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Colors.white.withOpacity(0.6), // pseudo-glass effect
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16), // perfectly rounded
        borderSide: BorderSide(color: AppColors.primary.withOpacity(0.08)), // subtle border
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: BorderSide(color: AppColors.primary.withOpacity(0.08)),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(16),
        borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
      ),
      labelStyle: TextStyle(color: AppColors.textMain.withOpacity(0.8), fontSize: 14),
      hintStyle: TextStyle(color: AppColors.textMuted.withOpacity(0.5)),
    ),
    cardTheme: CardThemeData(
      color: AppColors.cardBg, // Use the frosted surface color
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: AppColors.primary.withOpacity(0.05)), // elegant border
      ),
      margin: const EdgeInsets.only(bottom: 12),
    ),
  );
}
