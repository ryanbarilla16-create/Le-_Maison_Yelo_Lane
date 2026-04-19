import 'package:flutter/material.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
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
  // Coffee Brown Palette — slightly lighter, warmer tone
  static const Color primary      = Color(0xFF6D4C41); // Warm Coffee (lighter)
  static const Color primaryLight = Color(0xFF8D6E63); // Light Latte
  static const Color accent       = Color(0xFF8B634B); // Coffee Brown (Prices)
  static const Color success      = Color(0xFF2E7D32);
  static const Color warning      = Color(0xFFE8740C);
  static const Color danger       = Color(0xFFC62828);
  static const Color info         = Color(0xFF1565C0);
  static const Color gold         = Color(0xFFF9A825);

  // ── Button Gradient: #6D4C41 → #8D6E63 (warm coffee, slightly lighter than before) ──
  static const LinearGradient buttonGradient = LinearGradient(
    colors: [Color(0xFF6D4C41), Color(0xFF8D6E63)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  // Light Mode (Premium Latte)
  static const Color background = Color(0xFFFDFBF9);
  static const Color cardBg     = Color(0xFFF8F1EB);
  static const Color textMain   = Color(0xFF4A3B32);
  static const Color textMuted  = Color(0xFF8B634B);

  // Dark Mode (Deep Mocha)
  static const Color darkBg   = Color(0xFF1E1410);
  static const Color darkCard = Color(0xFF2D1F1A);
  static const Color darkText = Color(0xFFFDFBF9);
  static const Color darkMuted= Color(0xFFB59380);
}

// ═══ GRADIENT BUTTON WIDGET ═══
// Drop-in replacement for gradient styled buttons.
// Usage: GradientButton(label: 'Sign In', onPressed: _login)
// Usage with icon: GradientButton(label: 'Reserve', icon: Icons.calendar_today, onPressed: _book)
class GradientButton extends StatelessWidget {
  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final double height;
  final double radius;
  final bool isLoading;
  final double fontSize;

  const GradientButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon,
    this.height = 52,
    this.radius = 16,
    this.isLoading = false,
    this.fontSize = 15,
  });

  @override
  Widget build(BuildContext context) {
    final bool disabled = onPressed == null || isLoading;
    return SizedBox(
      width: double.infinity,
      height: height,
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: disabled
              ? const LinearGradient(colors: [Color(0xFFBCAAA4), Color(0xFFBCAAA4)])
              : AppColors.buttonGradient,
          borderRadius: BorderRadius.circular(radius),
          boxShadow: disabled
              ? []
              : [
                  BoxShadow(
                    color: AppColors.primary.withOpacity(0.30),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  ),
                ],
        ),
        child: MaterialButton(
          onPressed: disabled ? null : onPressed,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius)),
          elevation: 0,
          highlightElevation: 0,
          splashColor: Colors.white.withOpacity(0.15),
          highlightColor: Colors.white.withOpacity(0.08),
          child: isLoading
              ? const SizedBox(
                  width: 22,
                  height: 22,
                  child: SpinKitFadingCircle(
                    color: Colors.white,
                    size: 22.0,
                  ),
                )
              : Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (icon != null) ...[
                      Icon(icon, color: Colors.white, size: 19),
                      const SizedBox(width: 8),
                    ],
                    Text(
                      label,
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                        fontSize: fontSize,
                        letterSpacing: 0.3,
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}

// ═══ APP THEME DEFINITIONS ═══
class AppTheme {
  static ThemeData light = _buildTheme(isDark: false);
  static ThemeData dark  = _buildTheme(isDark: true);

  static ThemeData _buildTheme({required bool isDark}) {
    final baseColor  = isDark ? AppColors.darkText : AppColors.textMain;
    final mutedColor = isDark ? AppColors.darkMuted : AppColors.textMuted;
    final bgColor    = isDark ? AppColors.darkBg    : AppColors.background;
    final cardColor  = isDark ? AppColors.darkCard  : AppColors.cardBg;

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

      // ── AppBar ──
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

      // ── ElevatedButton: defaults to solid primary (gradient must use GradientButton) ──
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: Colors.white,
          elevation: 0,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          textStyle: const TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 15,
            letterSpacing: 0.3,
          ),
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
        ),
      ),

      // ── OutlinedButton ──
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.primary,
          side: const BorderSide(color: AppColors.primary, width: 1.5),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          textStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
          padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
        ),
      ),

      // ── TextButton ──
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AppColors.primary,
          textStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
        ),
      ),

      // ── Cards ──
      cardTheme: CardThemeData(
        color: cardColor,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: AppColors.primary.withOpacity(0.05)),
        ),
        margin: const EdgeInsets.only(bottom: 12),
      ),

      // ── Input Fields ──
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: isDark
            ? Colors.white.withOpacity(0.05)
            : Colors.white.withOpacity(0.75),
        contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        prefixIconColor: AppColors.primary,
        suffixIconColor: AppColors.textMuted,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: AppColors.primary.withOpacity(0.12)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: AppColors.primary.withOpacity(0.12)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.8),
        ),
        labelStyle: TextStyle(color: baseColor.withOpacity(0.75), fontSize: 14),
        hintStyle: TextStyle(color: mutedColor.withOpacity(0.5)),
      ),

      // ── Icon ──
      iconTheme: IconThemeData(color: AppColors.primary, size: 22),

      // ── Checkbox ──
      checkboxTheme: CheckboxThemeData(
        fillColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) return AppColors.primary;
          return Colors.transparent;
        }),
        side: const BorderSide(color: AppColors.primary, width: 1.5),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
      ),

      // ── ProgressIndicator ──
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppColors.primary,
      ),

      // ── Tabs ──
      tabBarTheme: TabBarThemeData(
        labelColor: AppColors.primary,
        unselectedLabelColor: mutedColor,
        indicatorColor: AppColors.primary,
        labelStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
        unselectedLabelStyle: const TextStyle(fontSize: 13),
      ),
    );
  }
}

// ═══ TEXT STYLES ═══
class AppTextStyles {
  static const TextStyle heading = TextStyle(
    fontFamily: 'Georgia',
    fontWeight: FontWeight.bold,
    color: AppColors.textMain,
  );
  static const TextStyle body = TextStyle(fontSize: 14, color: AppColors.textMain);
  static const TextStyle muted = TextStyle(fontSize: 13, color: AppColors.textMuted);
}

// ═══ DYNAMIC TEXT STYLES ═══
class ThemeText {
  static TextStyle heading(BuildContext context) => AppTextStyles.heading.copyWith(
    color: Theme.of(context).brightness == Brightness.dark
        ? AppColors.darkText
        : AppColors.textMain,
  );

  static TextStyle body(BuildContext context) => AppTextStyles.body.copyWith(
    color: Theme.of(context).brightness == Brightness.dark
        ? AppColors.darkText
        : AppColors.textMain,
  );

  static TextStyle muted(BuildContext context) => AppTextStyles.muted.copyWith(
    color: Theme.of(context).brightness == Brightness.dark
        ? AppColors.darkMuted
        : AppColors.textMuted,
  );
}
