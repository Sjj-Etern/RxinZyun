import 'dart:convert';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureStorage {
  static final SecureStorage _instance = SecureStorage._internal();
  final _storage = const FlutterSecureStorage();

  factory SecureStorage() {
    return _instance;
  }

  SecureStorage._internal();

  // JWT Token Management
  Future<void> saveToken(String token) async {
    await _storage.write(key: 'jwt_token', value: token);
  }

  Future<String?> getToken() async {
    return await _storage.read(key: 'jwt_token');
  }

  Future<void> deleteToken() async {
    await _storage.delete(key: 'jwt_token');
  }

  // User Info Management
  Future<void> saveUser(Map<String, dynamic> userMap) async {
    await _storage.write(key: 'user_info', value: jsonEncode(userMap));
  }

  Future<Map<String, dynamic>?> getUser() async {
    final userStr = await _storage.read(key: 'user_info');
    if (userStr != null) {
      try {
        return jsonDecode(userStr) as Map<String, dynamic>;
      } catch (_) {
        return null;
      }
    }
    return null;
  }

  Future<void> deleteUser() async {
    await _storage.delete(key: 'user_info');
  }

  // API Server Base URL Config
  Future<void> saveBaseUrl(String url) async {
    await _storage.write(key: 'custom_base_url', value: url);
  }

  Future<String?> getBaseUrl() async {
    return await _storage.read(key: 'custom_base_url');
  }

  // Clear All (Logout)
  Future<void> clearAll() async {
    await _storage.delete(key: 'jwt_token');
    await _storage.delete(key: 'user_info');
  }
}
