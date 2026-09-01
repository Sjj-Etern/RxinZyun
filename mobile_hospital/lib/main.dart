import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:his_mobile/core/theme/app_theme.dart';
import 'package:his_mobile/providers/auth_provider.dart';
import 'package:his_mobile/views/auth/login_page.dart';
import 'package:his_mobile/views/home/home_workbench.dart';

void main() {
  // 保证 Flutter 框架初始化完成
  WidgetsFlutterBinding.ensureInitialized();
  
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthProvider()..tryAutoLogin()),
      ],
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '智能HIS药房',
      debugShowCheckedModeBanner: false,
      
      // 应用定制主题样式
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: ThemeMode.system, // 跟随系统主题切换
      
      home: const AuthWrapper(),
    );
  }
}

class AuthWrapper extends StatelessWidget {
  const AuthWrapper({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    // 自动加载检测状态时显示进度条
    if (auth.isLoading && auth.currentUser == null) {
      return const Scaffold(
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text('正在载入就诊数据与服务器连接...', style: TextStyle(color: Colors.grey, fontSize: 14)),
            ],
          ),
        ),
      );
    }

    // 根据身份认证状态，自动切换至工作台或者登录页
    if (auth.isAuthenticated) {
      return const HomeWorkbench();
    } else {
      return const LoginPage();
    }
  }
}
