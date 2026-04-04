import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

// ═══ THEME MANAGER ═══
class ThemeManager extends ChangeNotifier {
  static final ThemeManager _instance = ThemeManager._internal();
  factory ThemeManager() => _instance;
  ThemeManager._internal();

  bool _isDark = false;
  bool get isDark => _isDark;

  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _isDark = prefs.getBool('isDark') ?? false;
    notifyListeners();
  }

  void toggleTheme() async {
    _isDark = !_isDark;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('isDark', _isDark);
    notifyListeners();
  }
}

// ═══ APP COLORS ═══
class AppColors {
  // Common
  static const Color primary = Color(0xFFA0522D);
  static const Color primaryLight = Color(0xFFBC6B4B); 
  static const Color accent = Color(0xFFD4A862);
  static const Color success = Color(0xFF5C3A21);
  static const Color warning = Color(0xFFA0522D); 
  static const Color danger = Color(0xFFC62828);
  static const Color info = Color(0xFFA0522D); 
  static const Color gold = Color(0xFFA0522D);

  // Light Mode (Premium Latte)
  static const Color background = Color(0xFFFDFBF9); 
  static const Color cardBg = Color(0xFFF8F1EB); 
  static const Color textMain = Color(0xFF4A3B32); 
  static const Color textMuted = Color(0xFFA0522D); 

  // Dark Mode (Deep Mocha)
  static const Color darkBg = Color(0xFF1E1410);
  static const Color darkCard = Color(0xFF2D1F1A);
  static const Color darkText = Color(0xFFFDFBF9);
  static const Color darkMuted = Color(0xFFB59380);
}

// ═══ APP THEME DEFINITIONS ═══
class AppTheme {
  static ThemeData light = _buildTheme(isDark: false);
  static ThemeData dark = _buildTheme(isDark: true);

  static ThemeData _buildTheme({required bool isDark}) {
    final baseColor = isDark ? AppColors.darkText : AppColors.textMain;
    final mutedColor = isDark ? AppColors.darkMuted : AppColors.textMuted;
    final bgColor = isDark ? AppColors.darkBg : AppColors.background;
    final cardColor = isDark ? AppColors.darkCard : AppColors.cardBg;

    return ThemeData(
      useMaterial3: true,
      fontFamily: 'Inter',
      brightness: isDark ? Brightness.dark : Brightness.light,
      scaffoldBackgroundColor: bgColor,
      primaryColor: AppColors.primary,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.primary,
        brightness: isDark ? Brightness.dark : Brightness.light,
        primary: AppColors.primary,
        secondary: AppColors.accent,
        surface: cardColor,
        background: bgColor,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        iconTheme: IconThemeData(color: baseColor),
        titleTextStyle: TextStyle(
          fontFamily: 'Georgia',
          fontWeight: FontWeight.bold,
          fontSize: 20,
          color: baseColor,
        ),
      ),
      cardTheme: CardThemeData(
        color: cardColor,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: AppColors.primary.withOpacity(0.05)),
        ),
        margin: const EdgeInsets.only(bottom: 12),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: isDark ? Colors.white.withOpacity(0.05) : Colors.white.withOpacity(0.6),
        contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: AppColors.primary.withOpacity(0.1)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: AppColors.primary.withOpacity(0.1)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
        ),
        labelStyle: TextStyle(color: baseColor.withOpacity(0.8), fontSize: 14),
        hintStyle: TextStyle(color: mutedColor.withOpacity(0.5)),
      ),
    );
  }
}

// Helper to keep old code working
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
}

// Use these for dynamic theming in new code
class ThemeText {
  static TextStyle heading(BuildContext context) => AppTextStyles.heading.copyWith(
    color: Theme.of(context).brightness == Brightness.dark ? AppColors.darkText : AppColors.textMain,
  );

  static TextStyle body(BuildContext context) => AppTextStyles.body.copyWith(
    color: Theme.of(context).brightness == Brightness.dark ? AppColors.darkText : AppColors.textMain,
  );

  static TextStyle muted(BuildContext context) => AppTextStyles.muted.copyWith(
    color: Theme.of(context).brightness == Brightness.dark ? AppColors.darkMuted : AppColors.textMuted,
  );
}


