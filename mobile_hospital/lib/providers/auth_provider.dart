import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/data/models/user_model.dart';
import 'package:his_mobile/data/storage/secure_storage.dart';

class AuthProvider extends ChangeNotifier {
  UserModel? _currentUser;
  bool _isLoading = false;
  String? _errorMsg;

  UserModel? get currentUser => _currentUser;
  bool get isLoading => _isLoading;
  String? get errorMsg => _errorMsg;
  bool get isAuthenticated => _currentUser != null;

  // 初始化方法：加载本地持久化的 token 并校验
  Future<void> tryAutoLogin() async {
    _isLoading = true;
    notifyListeners();

    // 先检查是否有自定义的 Base URL
    final customUrl = await SecureStorage().getBaseUrl();
    if (customUrl != null) {
      ApiClient().setBaseUrl(customUrl);
    }

    final token = await SecureStorage().getToken();
    if (token != null && token.isNotEmpty) {
      try {
        final response = await ApiClient().dio.get('/api/auth/me');
        if (response.statusCode == 200 && response.data['user'] != null) {
          _currentUser = UserModel.fromJson(response.data['user'] as Map<String, dynamic>);
        } else {
          await logout();
        }
      } catch (_) {
        // 如果离线或者校验出错，读取本地备份缓存，防止断网无法使用
        final localUser = await SecureStorage().getUser();
        if (localUser != null) {
          _currentUser = UserModel.fromJson(localUser);
        } else {
          await logout();
        }
      }
    }
    _isLoading = false;
    notifyListeners();
  }

  // 登录逻辑
  Future<bool> login(String username, String password) async {
    _isLoading = true;
    _errorMsg = null;
    notifyListeners();

    try {
      final response = await ApiClient().dio.post(
        '/api/auth/login',
        data: {'username': username, 'password': password},
      );

      if (response.statusCode == 200) {
        final token = response.data['token'] as String;
        final userJson = response.data['user'] as Map<String, dynamic>;

        // 存储凭证
        await SecureStorage().saveToken(token);
        await SecureStorage().saveUser(userJson);

        _currentUser = UserModel.fromJson(userJson);
        _isLoading = false;
        notifyListeners();
        return true;
      }
    } on DioException catch (e) {
      if (e.response != null && e.response!.data != null) {
        _errorMsg = e.response!.data['error']?.toString() ?? '用户名或密码错误';
      } else {
        _errorMsg = '网络连接失败，请检查服务器地址';
      }
    } catch (e) {
      _errorMsg = '未知系统错误';
    }

    _isLoading = false;
    notifyListeners();
    return false;
  }

  // 退出登录
  Future<void> logout() async {
    await SecureStorage().clearAll();
    _currentUser = null;
    _errorMsg = null;
    notifyListeners();
  }

  // 切换和保存服务器地址
  Future<void> updateServerAddress(String url) async {
    ApiClient().setBaseUrl(url);
    await SecureStorage().saveBaseUrl(url);
    notifyListeners();
  }
}
