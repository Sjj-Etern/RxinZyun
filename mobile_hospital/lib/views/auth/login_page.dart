import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/cupertino.dart';
import 'dart:ui';
import 'package:provider/provider.dart';
import 'package:his_mobile/providers/auth_provider.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/core/theme/glass_card.dart';
import 'package:his_mobile/core/widgets/animated_scale_button.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> with SingleTickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _obscurePassword = true;

  late AnimationController _logoController;
  late Animation<double> _logoScale;

  @override
  void initState() {
    super.initState();
    // Logo 呼吸微动效
    _logoController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    )..repeat(reverse: true);
    _logoScale = Tween<double>(begin: 0.96, end: 1.04).animate(
      CurvedAnimation(parent: _logoController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _logoController.dispose();
    super.dispose();
  }

  // 弹出服务器设置框（Cupertino 规范对话框）
  void _showServerSettings() {
    final controller = TextEditingController(text: ApiClient().baseUrl);
    showCupertinoDialog(
      context: context,
      builder: (context) {
        return CupertinoAlertDialog(
          title: const Text('服务器接口设置'),
          content: Padding(
            padding: const EdgeInsets.only(top: 12.0),
            child: Column(
              children: [
                const Text(
                  '请输入包含 http/https 的后端接口地址：', 
                  style: TextStyle(fontSize: 12, color: CupertinoColors.systemGrey),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 12),
                CupertinoTextField(
                  controller: controller,
                  placeholder: 'http://192.168.101.91:3001',
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: CupertinoDynamicColor.withBrightness(
                      color: CupertinoColors.white,
                      darkColor: CupertinoColors.black,
                    ),
                    border: Border.all(color: CupertinoColors.systemGrey4),
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
              ],
            ),
          ),
          actions: [
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () {
                final input = controller.text.trim();
                if (input.isNotEmpty) {
                  context.read<AuthProvider>().updateServerAddress(input);
                  HapticFeedback.mediumImpact();
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('服务器接口已切换至: $input'), backgroundColor: const Color(0xFF00796B)),
                  );
                }
                Navigator.pop(context);
              },
              child: const Text('保存'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _handleLogin() async {
    if (!_formKey.currentState!.validate()) {
      HapticFeedback.heavyImpact();
      return;
    }
    
    HapticFeedback.mediumImpact();
    final auth = context.read<AuthProvider>();
    final success = await auth.login(
      _usernameController.text.trim(),
      _passwordController.text,
    );

    if (success && mounted) {
      HapticFeedback.mediumImpact();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('登录成功，欢迎使用智能HIS药房！'), backgroundColor: Color(0xFF30D158)),
      );
    } else if (mounted) {
      HapticFeedback.heavyImpact();
      showCupertinoDialog(
        context: context,
        builder: (context) => CupertinoAlertDialog(
          title: const Text('登录失败'),
          content: Text(auth.errorMsg ?? '无法连接到服务器，请检查接口地址配置'),
          actions: [
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.pop(context),
              child: const Text('好的'),
            ),
          ],
        ),
      );
    }
  }

  Widget _buildBackgroundGlows(bool isDark) {
    if (!isDark) {
      return Stack(
        children: [
          Positioned(
            top: -100,
            left: -100,
            child: Container(
              width: 320,
              height: 320,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFF009688).withValues(alpha: 0.22),
              ),
            ),
          ),
          Positioned(
            bottom: 120,
            right: -120,
            child: Container(
              width: 360,
              height: 360,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFF7B1FA2).withValues(alpha: 0.16),
              ),
            ),
          ),
        ],
      );
    }
    return Stack(
      children: [
        Positioned(
          top: -120,
          left: -80,
          child: Container(
            width: 340,
            height: 340,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF009688).withValues(alpha: 0.18),
            ),
          ),
        ),
        Positioned(
          top: 240,
          right: -100,
          child: Container(
            width: 320,
            height: 320,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF7B1FA2).withValues(alpha: 0.14),
            ),
          ),
        ),
        Positioned(
          bottom: -150,
          left: -100,
          child: Container(
            width: 400,
            height: 400,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: const Color(0xFF0288D1).withValues(alpha: 0.16),
            ),
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final isLoading = context.watch<AuthProvider>().isLoading;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      body: Stack(
        children: [
          Positioned.fill(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: isDark 
                      ? [const Color(0xFF090C15), const Color(0xFF0B1B2A), const Color(0xFF141221)]
                      : [const Color(0xFFEAF6FF), const Color(0xFFEDFDF8), const Color(0xFFFFF2F7)],
                ),
              ),
            ),
          ),
          Positioned.fill(child: _buildBackgroundGlows(isDark)),
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 80, sigmaY: 80),
              child: Container(color: Colors.transparent),
            ),
          ),
          Positioned.fill(
            child: SafeArea(
              child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
              child: Form(
                key: _formKey,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // 顶部设置按钮
                    Align(
                      alignment: Alignment.topRight,
                      child: IconButton(
                        icon: Icon(CupertinoIcons.settings, color: isDark ? Colors.white70 : Colors.black54),
                        onPressed: _showServerSettings,
                      ),
                    ),
                    const SizedBox(height: 10),
                    
                    // Logo 和应用名称 (呼吸效果)
                    AnimatedBuilder(
                      animation: _logoScale,
                      builder: (context, child) {
                        return Transform.scale(
                          scale: _logoScale.value,
                          child: Hero(
                            tag: 'app_logo',
                            child: Image.asset(
                              'assets/app_icon.png',
                              height: 105,
                              fit: BoxFit.contain,
                            ),
                          ),
                        );
                      },
                    ),
                    const SizedBox(height: 20),
                    Text(
                      '智能HIS药房系统',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.w900,
                        color: isDark ? Colors.white : const Color(0xFF0B1B2A),
                        letterSpacing: 1.5,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      '自动化配药与追溯码流程闭环复核',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w500,
                        color: isDark ? Colors.white60 : Colors.black54,
                      ),
                    ),
                    
                    // 将输入区包裹在宽敞的磨砂玻璃卡片中
                    GlassCard(
                      margin: const EdgeInsets.only(top: 32),
                      padding: const EdgeInsets.all(24.0),
                      borderRadius: 28,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          const Text(
                            '安全凭证登录',
                            style: TextStyle(fontSize: 15, fontWeight: FontWeight.w900, color: Colors.grey),
                          ),
                          const SizedBox(height: 20),

                          Container(
                            decoration: BoxDecoration(
                              color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.04),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            padding: const EdgeInsets.symmetric(horizontal: 12),
                            child: TextFormField(
                              controller: _usernameController,
                              keyboardType: TextInputType.text,
                              style: TextStyle(color: isDark ? Colors.white : Colors.black87),
                              decoration: InputDecoration(
                                border: InputBorder.none,
                                enabledBorder: InputBorder.none,
                                focusedBorder: InputBorder.none,
                                errorBorder: InputBorder.none,
                                focusedErrorBorder: InputBorder.none,
                                filled: false,
                                prefixIcon: Icon(CupertinoIcons.person, color: isDark ? Colors.white60 : Colors.black45),
                                labelText: '用户名',
                                labelStyle: const TextStyle(fontSize: 13, color: Colors.grey),
                                hintText: '请输入账号 (如 doctor1)',
                                hintStyle: const TextStyle(fontSize: 12, color: Colors.grey),
                              ),
                              validator: (value) {
                                if (value == null || value.trim().isEmpty) {
                                  return '请输入您的用户名';
                                }
                                return null;
                              },
                            ),
                          ),
                          const SizedBox(height: 16),

                          Container(
                            decoration: BoxDecoration(
                              color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.04),
                              borderRadius: BorderRadius.circular(16),
                            ),
                            padding: const EdgeInsets.symmetric(horizontal: 12),
                            child: TextFormField(
                              controller: _passwordController,
                              obscureText: _obscurePassword,
                              style: TextStyle(color: isDark ? Colors.white : Colors.black87),
                              decoration: InputDecoration(
                                border: InputBorder.none,
                                enabledBorder: InputBorder.none,
                                focusedBorder: InputBorder.none,
                                errorBorder: InputBorder.none,
                                focusedErrorBorder: InputBorder.none,
                                filled: false,
                                prefixIcon: Icon(CupertinoIcons.lock, color: isDark ? Colors.white60 : Colors.black45),
                                suffixIcon: IconButton(
                                  icon: Icon(
                                    _obscurePassword ? CupertinoIcons.eye_slash : CupertinoIcons.eye,
                                    color: isDark ? Colors.white60 : Colors.black45,
                                    size: 20,
                                  ),
                                  onPressed: () {
                                    setState(() {
                                      _obscurePassword = !_obscurePassword;
                                    });
                                  },
                                ),
                                labelText: '密码',
                                labelStyle: const TextStyle(fontSize: 13, color: Colors.grey),
                                hintText: '请输入密码',
                                hintStyle: const TextStyle(fontSize: 12, color: Colors.grey),
                              ),
                              validator: (value) {
                                if (value == null || value.isEmpty) {
                                  return '请输入您的密码';
                                }
                                return null;
                              },
                            ),
                          ),
                          const SizedBox(height: 28),

                          // 弹性登录按钮
                          isLoading
                              ? const Center(child: CircularProgressIndicator(color: Color(0xFF009688)))
                              : AnimatedScaleButton(
                                  onTap: _handleLogin,
                                  child: Container(
                                    height: 52,
                                    decoration: BoxDecoration(
                                      gradient: const LinearGradient(
                                        colors: [Color(0xFF009688), Color(0xFF00796B)],
                                      ),
                                      borderRadius: BorderRadius.circular(20),
                                      boxShadow: [
                                        BoxShadow(
                                          color: const Color(0xFF009688).withValues(alpha: 0.25),
                                          blurRadius: 12,
                                          offset: const Offset(0, 4),
                                        ),
                                      ],
                                    ),
                                    alignment: Alignment.center,
                                    child: const Text(
                                      '安全登录',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontSize: 15,
                                        fontWeight: FontWeight.w900,
                                        letterSpacing: 2.0,
                                      ),
                                    ),
                                  ),
                                ),
                          const SizedBox(height: 20),
                          
                          // 协议提示
                          Text(
                            '登录即代表您同意 HIS 系统安全审计与保密协议',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.w500,
                              color: isDark ? Colors.white30 : Colors.black38,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    ],
  ),
);
  }
}
