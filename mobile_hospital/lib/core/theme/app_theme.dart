import 'package:flutter/material.dart';

class AppTheme {
  // 定义主题色板 - 经典现代医疗深海蓝/翠绿配色
  static const Color primaryColor = Color(0xFF009688); // 更加透亮明朗的医用翠绿
  static const Color accentColor = Color(0xFF007AFF);  // 经典 iOS 科技蓝
  static const Color backgroundColor = Color(0xFFF5F5F7); // 苹果极简银灰色
  static const Color darkBackgroundColor = Color(0xFF090C15); // 更深邃高级的太空深邃黑

  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: primaryColor,
        primary: primaryColor,
        secondary: accentColor,
        surface: Colors.white,
      ),
      scaffoldBackgroundColor: backgroundColor,
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: TextStyle(
          color: Color(0xFF1E293B),
          fontSize: 20,
          fontWeight: FontWeight.w800, // 更大字重
          letterSpacing: 0.5,
        ),
        iconTheme: IconThemeData(color: Color(0xFF1E293B)),
      ),
      cardTheme: const CardThemeData(
        color: Colors.white,
        elevation: 0, // 扁平化浮空
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(20))), // 更圆润大角
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primaryColor,
          foregroundColor: Colors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 28),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)), // 苹果圆角药丸
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: 0.8),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.6), // 亮色磨砂半透底
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: Colors.black12, width: 1.0),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: Colors.black12, width: 1.0),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: primaryColor, width: 1.5),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        labelStyle: const TextStyle(color: Colors.black54, fontSize: 14),
      ),
    );
  }

  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        brightness: Brightness.dark,
        seedColor: primaryColor,
        primary: primaryColor,
        secondary: accentColor,
        surface: const Color(0xFF1E293B),
      ),
      scaffoldBackgroundColor: darkBackgroundColor,
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
        titleTextStyle: TextStyle(
          color: Colors.white,
          fontSize: 20,
          fontWeight: FontWeight.w800,
          letterSpacing: 0.5,
        ),
        iconTheme: IconThemeData(color: Colors.white),
      ),
      cardTheme: const CardThemeData(
        color: Color(0xFF1E293B),
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(20))),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primaryColor,
          foregroundColor: Colors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 28),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: 0.8),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white.withValues(alpha: 0.05), // 暗色磨砂半透底
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: Colors.white12, width: 1.0),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: Colors.white12, width: 1.0),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: primaryColor, width: 1.5),
        ),
        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
        labelStyle: const TextStyle(color: Colors.white60, fontSize: 14),
      ),
    );
  }
}
