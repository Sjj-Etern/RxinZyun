import 'dart:io';
import 'package:dio/dio.dart';
import 'package:dio/io.dart';
import 'package:his_mobile/data/storage/secure_storage.dart';

class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  late final Dio dio;
  
  // 默认指向局域网中的 HIS Node.js Server
  String _baseUrl = 'http://192.168.101.26:3001';

  factory ApiClient() {
    return _instance;
  }

  ApiClient._internal() {
    dio = Dio(BaseOptions(
      baseUrl: _baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
      contentType: Headers.jsonContentType,
    ));

    // 配置 HTTPS 证书信任（核心：iOS/Android 本地网络自签名证书校验放行）
    dio.httpClientAdapter = IOHttpClientAdapter(
      createHttpClient: () {
        final client = HttpClient();
        client.badCertificateCallback = (X509Certificate cert, String host, int port) {
          // 允许开发测试环境下的所有 https 自签名证书
          return true;
        };
        return client;
      },
    );

    // 注册拦截器：自动注入 JWT Token
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await SecureStorage().getToken();
        if (token != null && token.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        return handler.next(options);
      },
      onError: (DioException e, handler) {
        // 可以在这里做全局错误处理，比如 401 自动登出
        return handler.next(e);
      },
    ));
  }

  String get baseUrl => _baseUrl;

  void setBaseUrl(String url) {
    if (url.endsWith('/')) {
      _baseUrl = url.substring(0, url.length - 1);
    } else {
      _baseUrl = url;
    }
    dio.options.baseUrl = _baseUrl;
  }
}
