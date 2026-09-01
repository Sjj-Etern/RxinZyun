import 'dart:async';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/providers/auth_provider.dart';
import 'package:his_mobile/data/models/prescription_model.dart';
import 'package:his_mobile/views/patient/patient_list_page.dart';
import 'package:his_mobile/views/medicine/medicine_list_page.dart';
import 'package:his_mobile/views/prescription/prescription_create_page.dart';
import 'package:his_mobile/views/prescription/prescription_detail_page.dart';
import 'package:his_mobile/core/theme/glass_card.dart';
import 'package:his_mobile/core/widgets/animated_scale_button.dart';
import 'package:his_mobile/views/auth/face_auth_page.dart';
import 'package:his_mobile/views/delivery/delivery_records_page.dart';
import 'package:his_mobile/views/dispense/dispense_management_page.dart';
import 'package:his_mobile/views/robot/robot_management_page.dart';
import 'package:his_mobile/views/prescription/scan_page.dart';

class HomeWorkbench extends StatefulWidget {
  const HomeWorkbench({super.key});

  @override
  State<HomeWorkbench> createState() => _HomeWorkbenchState();
}

class _HomeWorkbenchState extends State<HomeWorkbench> {
  int _currentIndex = 0;

  // 定时更新顶部时间
  late Timer _timeTimer;
  String _timeString = '';

  // 动态数据指标
  int _readyPrescriptions = 0;
  int _totalMedicines = 0;
  int _totalPatients = 0;
  List<PrescriptionModel> _recentPrescriptions = [];
  bool _toolsExpanded = false;

  @override
  void initState() {
    super.initState();
    _updateTime();
    _timeTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (mounted) {
        _updateTime();
      }
    });
    // 获取实时看板数据
    _fetchStats();
  }

  @override
  void dispose() {
    _timeTimer.cancel();
    super.dispose();
  }

  void _updateTime() {
    final now = DateTime.now();
    setState(() {
      _timeString = '${now.year}-${now.month.toString().padLeft(2, '0')}-${now.day.toString().padLeft(2, '0')} '
          '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}:${now.second.toString().padLeft(2, '0')}';
    });
  }

  // 从后端获取待发药处方数、药品数、病人总数，以及最新处方列表
  Future<void> _fetchStats() async {
    try {
      final dio = ApiClient().dio;
      // 1. 待发药处方
      final resPres = await dio.get('/api/prescriptions', queryParameters: {'status': 'approved', 'pageSize': 1});
      // 2. 药品总类
      final resMed = await dio.get('/api/medicines', queryParameters: {'pageSize': 1});
      // 3. 在册病人
      final resPat = await dio.get('/api/patients', queryParameters: {'pageSize': 1});
      // 4. 最新处方列表
      final resRecent = await dio.get('/api/prescriptions', queryParameters: {'pageSize': 5});

      if (mounted) {
        final list = resRecent.data['list'] as List? ?? [];
        setState(() {
          _readyPrescriptions = resPres.data['total'] as int? ?? 0;
          _totalMedicines = resMed.data['total'] as int? ?? 0;
          _totalPatients = resPat.data['total'] as int? ?? 0;
          _recentPrescriptions = list.map((p) => PrescriptionModel.fromJson(p as Map<String, dynamic>)).toList();
        });
      }
    } catch (_) {}
  }

  // 切换分区
  void _onTabTapped(int index) {
    HapticFeedback.selectionClick();
    setState(() {
      _currentIndex = index;
    });
    if (index == 0) {
      _fetchStats(); // 每次回到工作版刷新指标
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final user = auth.currentUser;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    if (user == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    // 根据 Tab 导航获取当前主界面
    Widget currentBody;
    switch (_currentIndex) {
      case 0:
        currentBody = _buildWorkbenchView(auth);
        break;
      case 1:
        currentBody = user.isDoctor || user.role == 'admin'
            ? const PrescriptionCreatePage()
            : _buildNoPermissionView('医生');
        break;
      case 2:
        currentBody = const ScanPage();
        break;
      case 3:
        currentBody = user.isDoctor || user.role == 'admin'
            ? const PatientListPage()
            : _buildNoPermissionView('医生');
        break;
      case 4:
        currentBody = const MedicineListPage(); // 所有人可查看药品管理
        break;
      default:
        currentBody = _buildWorkbenchView(auth);
    }

    return Scaffold(
      extendBody: true, // 让页面流延到悬浮底栏下方
      body: Stack(
        children: [
          Positioned.fill(
            child: currentBody,
          ),
          // 悬浮式毛玻璃底栏
          Positioned(
            left: 20,
            right: 20,
            bottom: 24,
            child: _buildFloatingBottomBar(isDark),
          ),
        ],
      ),
    );
  }

  // 渲染苹果悬浮磨砂底栏 (Cupertino Navigation Elements)
  Widget _buildFloatingBottomBar(bool isDark) {
    final List<Map<String, dynamic>> items = [
      {'icon': CupertinoIcons.square_grid_2x2, 'activeIcon': CupertinoIcons.square_grid_2x2_fill, 'label': '工作台'},
      {'icon': CupertinoIcons.plus_rectangle, 'activeIcon': CupertinoIcons.plus_rectangle_fill, 'label': '开具'},
      {'icon': CupertinoIcons.barcode_viewfinder, 'activeIcon': CupertinoIcons.barcode_viewfinder, 'label': '出库追溯'},
      {'icon': CupertinoIcons.person_2, 'activeIcon': CupertinoIcons.person_2_fill, 'label': '病人'},
      {'icon': CupertinoIcons.bandage, 'activeIcon': CupertinoIcons.bandage_fill, 'label': '药品'},
    ];

    return Container(
      decoration: BoxDecoration(
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDark ? 0.4 : 0.08),
            blurRadius: 28,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(28),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
          child: Container(
            height: 68,
            padding: const EdgeInsets.symmetric(horizontal: 10),
            decoration: BoxDecoration(
              color: isDark 
                  ? const Color(0xFF1E293B).withValues(alpha: 0.35) 
                  : Colors.white.withValues(alpha: 0.45),
              borderRadius: BorderRadius.circular(28),
              border: Border.all(
                color: isDark 
                    ? Colors.white.withValues(alpha: 0.12) 
                    : Colors.white.withValues(alpha: 0.5),
                width: 0.8,
              ),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: List.generate(items.length, (index) {
                final isSelected = _currentIndex == index;
                final item = items[index];
                return Expanded(
                  child: AnimatedScaleButton(
                    onTap: () => _onTabTapped(index),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          isSelected ? item['activeIcon'] as IconData : item['icon'] as IconData,
                          color: isSelected 
                              ? const Color(0xFF009688) 
                              : (isDark ? Colors.white54 : Colors.black45),
                          size: 22,
                        ),
                        const SizedBox(height: 4),
                        Text(
                          item['label'] as String,
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: isSelected ? FontWeight.w900 : FontWeight.normal,
                            color: isSelected 
                                ? const Color(0xFF009688) 
                                : (isDark ? Colors.white54 : Colors.black54),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ),
          ),
        ),
      ),
    );
  }

  // 苹果极高水准 Aurora 背景光晕
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

  // 渲染 Tab 0: 工作版 (苹果极简极宽舒设计)
  Widget _buildWorkbenchView(AuthProvider auth) {
    final user = auth.currentUser!;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: isDark
              ? [const Color(0xFF090C15), const Color(0xFF0B1B2A), const Color(0xFF141221)]
              : [const Color(0xFFEAF6FF), const Color(0xFFEDFDF8), const Color(0xFFFFF2F7)],
        ),
      ),
      child: Stack(
        children: [
          // 极光光晕背景
          Positioned.fill(child: _buildBackgroundGlows(isDark)),
          Positioned.fill(
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 80, sigmaY: 80),
              child: Container(color: Colors.transparent),
            ),
          ),
          // 页面主体
          SafeArea(
            bottom: false,
            child: RefreshIndicator(
              onRefresh: _fetchStats,
              color: const Color(0xFF009688),
              child: CustomScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                slivers: [
                  // 1. 顶部大标题 + 头像 (苹果风格宽敞头部)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(20.0, 24.0, 20.0, 16.0),
                      child: Row(
                        children: [
                          CircleAvatar(
                            radius: 24,
                            backgroundColor: const Color(0xFF00796B),
                            child: Text(
                              user.realName.isNotEmpty ? user.realName.substring(0, 1) : '药',
                              style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold),
                            ),
                          ),
                          const SizedBox(width: 14),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '仁爱医院 HIS',
                                  style: TextStyle(
                                    fontSize: 22,
                                    fontWeight: FontWeight.w900,
                                    color: isDark ? Colors.white : const Color(0xFF0B1B2A),
                                    letterSpacing: 0.5,
                                  ),
                                ),
                                const SizedBox(height: 2),
                                Text(
                                  '欢迎，${user.realName} (${user.role == 'doctor' ? '医生' : '药师'}) · $_timeString',
                                  style: TextStyle(
                                    fontSize: 11,
                                    fontWeight: FontWeight.w500,
                                    color: isDark ? Colors.white60 : Colors.black54,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          IconButton(
                            icon: const Icon(CupertinoIcons.square_arrow_right, color: Colors.redAccent, size: 22),
                            onPressed: () {
                              HapticFeedback.heavyImpact();
                              auth.logout();
                            },
                            tooltip: '退出登录',
                          ),
                        ],
                      ),
                    ),
                  ),

                  // 2. iOS 风格 Stats 看板 (待发药 / 药品 / 病人 整合)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 8.0),
                      child: Row(
                        children: [
                          // 待发药 (大卡片)
                          Expanded(
                            flex: 5,
                            child: AnimatedScaleButton(
                              onTap: () => _onTabTapped(2),
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 16.0),
                                decoration: BoxDecoration(
                                  gradient: LinearGradient(
                                    colors: isDark 
                                        ? [const Color(0xFF00796B).withValues(alpha: 0.35), const Color(0xFF004D40).withValues(alpha: 0.15)]
                                        : [const Color(0xFFE0F2F1), const Color(0xFFB2DFDB)],
                                  ),
                                  borderRadius: BorderRadius.circular(22),
                                  border: Border.all(
                                    color: isDark 
                                      ? const Color(0xFF00796B).withValues(alpha: 0.45) 
                                      : const Color(0xFF00796B).withValues(alpha: 0.25),
                                    width: 1.0,
                                  ),
                                  boxShadow: [
                                    BoxShadow(
                                      color: const Color(0xFF00796B).withValues(alpha: isDark ? 0.12 : 0.05),
                                      blurRadius: 16,
                                      offset: const Offset(0, 8),
                                    )
                                  ]
                                ),
                                child: Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          '$_readyPrescriptions',
                                          style: TextStyle(
                                            fontSize: 30,
                                            fontWeight: FontWeight.w900,
                                            color: isDark ? const Color(0xFF4DB6AC) : const Color(0xFF00796B),
                                          ),
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          '待发药处方',
                                          style: TextStyle(
                                            color: isDark ? const Color(0xFF80CBC4) : const Color(0xFF00796B),
                                            fontSize: 11,
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                      ],
                                    ),
                                    Icon(
                                      CupertinoIcons.time,
                                      color: isDark ? const Color(0xFF4DB6AC) : const Color(0xFF00796B),
                                      size: 26,
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 12),
                          // 药品与病人 (双卡)
                          Expanded(
                            flex: 6,
                            child: Row(
                              children: [
                                Expanded(
                                  child: AnimatedScaleButton(
                                    onTap: () => _onTabTapped(4),
                                    child: Container(
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(20),
                                        gradient: LinearGradient(
                                          colors: isDark
                                              ? [const Color(0xFF7B1FA2).withValues(alpha: 0.25), Colors.white.withValues(alpha: 0.02)]
                                              : [const Color(0xFFF3E5F5), Colors.white.withValues(alpha: 0.8)],
                                        ),
                                        border: Border.all(
                                          color: isDark ? const Color(0xFF7B1FA2).withValues(alpha: 0.35) : const Color(0xFFE1BEE7),
                                        ),
                                      ),
                                      padding: const EdgeInsets.all(12.0),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            '$_totalMedicines',
                                            style: const TextStyle(
                                              fontSize: 20,
                                              fontWeight: FontWeight.w900,
                                              color: Color(0xFFAB47BC),
                                            ),
                                          ),
                                          const SizedBox(height: 2),
                                          const Text(
                                            '药品品类',
                                            style: TextStyle(color: Colors.grey, fontSize: 10, fontWeight: FontWeight.bold),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: AnimatedScaleButton(
                                    onTap: () => _onTabTapped(3),
                                    child: Container(
                                      decoration: BoxDecoration(
                                        borderRadius: BorderRadius.circular(20),
                                        gradient: LinearGradient(
                                          colors: isDark
                                              ? [const Color(0xFF0288D1).withValues(alpha: 0.25), Colors.white.withValues(alpha: 0.02)]
                                              : [const Color(0xFFE1F5FE), Colors.white.withValues(alpha: 0.8)],
                                        ),
                                        border: Border.all(
                                          color: isDark ? const Color(0xFF0288D1).withValues(alpha: 0.35) : const Color(0xFFB3E5FC),
                                        ),
                                      ),
                                      padding: const EdgeInsets.all(12.0),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            '$_totalPatients',
                                            style: const TextStyle(
                                              fontSize: 20,
                                              fontWeight: FontWeight.w900,
                                              color: Color(0xFF29B6F6),
                                            ),
                                          ),
                                          const SizedBox(height: 2),
                                          const Text(
                                            '在册病人',
                                            style: TextStyle(color: Colors.grey, fontSize: 10, fontWeight: FontWeight.bold),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),

                  // 3. 核心功能大药丸面板 (2列精美宽舒渐变布局)
                  SliverPadding(
                    padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 16.0),
                    sliver: SliverGrid(
                      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: 2,
                        crossAxisSpacing: 16,
                        mainAxisSpacing: 16,
                        childAspectRatio: 1.22,
                      ),
                      delegate: SliverChildListDelegate([
                        _buildActionCard(
                          title: '开具处方',
                          subtitle: '临床医生新开方',
                          icon: CupertinoIcons.plus_rectangle,
                          color: const Color(0xFF009688),
                          onTap: () => _onTabTapped(1),
                        ),
                        _buildActionCard(
                          title: '出库追溯',
                          subtitle: '扫码出库与接收确认',
                          icon: CupertinoIcons.barcode_viewfinder,
                          color: const Color(0xFF0F766E),
                          onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const ScanPage())),
                        ),
                        _buildActionCard(
                          title: '病人档案',
                          subtitle: '就诊人信息与建档',
                          icon: CupertinoIcons.person_crop_square,
                          color: const Color(0xFF0288D1),
                          onTap: () => _onTabTapped(3),
                        ),
                        _buildActionCard(
                          title: '药品总览',
                          subtitle: '药品名录及库存数',
                          icon: CupertinoIcons.bandage,
                          color: const Color(0xFF7B1FA2),
                          onTap: () => _onTabTapped(4),
                        ),
                        _buildActionCard(
                          title: '身份认证',
                          subtitle: '录入人脸用于核验',
                          icon: CupertinoIcons.person_crop_circle_badge_checkmark,
                          color: const Color(0xFF0288D1),
                          onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const FaceAuthPage())),
                        ),
                        _buildActionCard(
                          title: '配送记录',
                          subtitle: '到达通知与实时扫脸开锁',
                          icon: CupertinoIcons.cube_box,
                          color: const Color(0xFF00897B),
                          onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const DeliveryRecordsPage())),
                        ),
                        if (user.isPharmacist)
                          _buildActionCard(
                            title: '发药管理',
                            subtitle: '选择机器人确认发药',
                            icon: CupertinoIcons.paperplane,
                            color: const Color(0xFF0F766E),
                            onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const DispenseManagementPage())),
                          ),
                        _buildActionCard(
                          title: '机器人管理',
                          subtitle: user.isAdmin ? '设备维护与测试恢复' : '查看设备调度状态',
                          icon: CupertinoIcons.device_laptop,
                          color: const Color(0xFF2563EB),
                          onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const RobotManagementPage())),
                        ),
                      ]),
                    ),
                  ),

                  // 4. 更多辅助工具折叠抽屉 (Cupertino style)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 4.0),
                      child: GlassCard(
                        margin: EdgeInsets.zero,
                        padding: EdgeInsets.zero,
                        borderRadius: 22,
                        child: Theme(
                          data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
                          child: ExpansionTile(
                            title: Text(
                              '更多临床与管理工具',
                              style: TextStyle(
                                fontSize: 13,
                                fontWeight: FontWeight.w900,
                                color: isDark ? Colors.white70 : const Color(0xFF0B1B2A),
                              ),
                            ),
                            leading: const Icon(CupertinoIcons.grid, color: Colors.grey, size: 18),
                            trailing: Icon(
                              _toolsExpanded ? CupertinoIcons.chevron_up : CupertinoIcons.chevron_down,
                              color: Colors.grey,
                              size: 16,
                            ),
                            onExpansionChanged: (expanded) {
                              setState(() {
                                _toolsExpanded = expanded;
                              });
                            },
                            children: [
                              Padding(
                                padding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
                                child: GridView.count(
                                  shrinkWrap: true,
                                  physics: const NeverScrollableScrollPhysics(),
                                  crossAxisCount: 4,
                                  crossAxisSpacing: 10,
                                  mainAxisSpacing: 16,
                                  childAspectRatio: 0.9,
                                  children: [
                                    _buildMinorTool('医院取药', CupertinoIcons.location_fill),
                                    _buildMinorTool('报表生成', CupertinoIcons.chart_bar_fill),
                                    _buildMinorTool('药盒设置', CupertinoIcons.settings),
                                    _buildMinorTool('操作记录', CupertinoIcons.time),
                                    _buildMinorTool('药品下架', CupertinoIcons.arrow_down),
                                    _buildMinorTool('补药汇总', CupertinoIcons.plus_rectangle_fill),
                                    _buildMinorTool('库存查询', CupertinoIcons.search),
                                  ],
                                ),
                              )
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),

                  // 5. 最近处方板块 (完全舒展开)
                  SliverToBoxAdapter(
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(20.0, 28.0, 20.0, 10.0),
                      child: Row(
                        children: [
                          const Icon(CupertinoIcons.time, color: Color(0xFF00796B), size: 18),
                          const SizedBox(width: 8),
                          Text(
                            '最近处方',
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w900,
                              color: isDark ? Colors.white : const Color(0xFF1E293B),
                              letterSpacing: 0.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),

                  SliverPadding(
                    padding: const EdgeInsets.fromLTRB(20.0, 0, 20.0, 110.0), // 留空给悬浮底栏
                    sliver: SliverToBoxAdapter(
                      child: _recentPrescriptions.isEmpty
                          ? const GlassCard(
                              margin: EdgeInsets.zero,
                              padding: EdgeInsets.all(28.0),
                              borderRadius: 20,
                              child: Center(
                                child: Text('暂无最新处方记录', style: TextStyle(color: Colors.grey, fontSize: 13)),
                              ),
                            )
                          : GlassCard(
                              margin: EdgeInsets.zero,
                              padding: const EdgeInsets.symmetric(vertical: 8),
                              borderRadius: 22,
                              child: ListView.separated(
                                shrinkWrap: true,
                                physics: const NeverScrollableScrollPhysics(),
                                itemCount: _recentPrescriptions.length,
                                separatorBuilder: (context, idx) => const Divider(height: 1, color: Colors.black12),
                                itemBuilder: (context, idx) {
                                  final p = _recentPrescriptions[idx];
                                  
                                  // 状态对应的中文文本与颜色
                                  String statusText = p.statusText;
                                  Color statusColor = Colors.grey;
                                  switch (p.status) {
                                    case 'pending':
                                      statusColor = const Color(0xFFFF9F0A);
                                      break;
                                    case 'approved':
                                      statusColor = const Color(0xFF007AFF);
                                      break;
                                    case 'dispensing':
                                      statusColor = const Color(0xFFBF5AF2);
                                      break;
                                    case 'completed':
                                      statusColor = const Color(0xFF30D158);
                                      break;
                                    case 'rejected':
                                      statusColor = const Color(0xFFFF453A);
                                      break;
                                  }

                                  return ListTile(
                                    contentPadding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 8.0),
                                    title: Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        Text(
                                          '${p.patientName ?? "未知"} (${p.patientGender ?? "未知"} · ${p.patientAge ?? "未知"}岁)',
                                          style: TextStyle(
                                            fontWeight: FontWeight.w900, 
                                            fontSize: 14,
                                            color: isDark ? Colors.white : const Color(0xFF1E293B),
                                          ),
                                        ),
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                          decoration: BoxDecoration(
                                            color: statusColor.withValues(alpha: 0.12),
                                            borderRadius: BorderRadius.circular(8),
                                            border: Border.all(color: statusColor.withValues(alpha: 0.25), width: 0.8),
                                          ),
                                          child: Row(
                                            mainAxisSize: MainAxisSize.min,
                                            children: [
                                              Container(
                                                width: 5,
                                                height: 5,
                                                decoration: BoxDecoration(
                                                  shape: BoxShape.circle,
                                                  color: statusColor,
                                                ),
                                              ),
                                              const SizedBox(width: 5),
                                              Text(
                                                statusText,
                                                style: TextStyle(color: statusColor, fontSize: 10, fontWeight: FontWeight.w900),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ],
                                    ),
                                    subtitle: Padding(
                                      padding: const EdgeInsets.only(top: 8.0),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            '处方编号: ${p.prescriptionCode}',
                                            style: const TextStyle(fontSize: 12, color: Colors.grey),
                                          ),
                                          const SizedBox(height: 4),
                                          Text(
                                            '临床诊断: ${p.diagnosis ?? "未录入"} | 医生: ${p.doctorName ?? "管理员"}',
                                            style: TextStyle(
                                              fontSize: 12, 
                                              color: isDark ? Colors.white60 : Colors.black54,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                    onTap: () {
                                      Navigator.push(
                                        context,
                                        MaterialPageRoute(
                                          builder: (context) => PrescriptionDetailPage(prescriptionId: p.id),
                                        ),
                                      ).then((_) => _fetchStats()); // 返回时自动刷新
                                    },
                                  );
                                },
                              ),
                            ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  // 构建核心大功能卡片的方法 (高级渐变玻璃拟态)
  Widget _buildActionCard({
    required String title,
    required String subtitle,
    required IconData icon,
    required Color color,
    required VoidCallback onTap,
  }) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return AnimatedScaleButton(
      onTap: onTap,
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(22),
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: isDark
                ? [
                    color.withValues(alpha: 0.15),
                    Colors.white.withValues(alpha: 0.03),
                  ]
                : [
                    color.withValues(alpha: 0.08),
                    Colors.white.withValues(alpha: 0.7),
                  ],
          ),
          border: Border.all(
            color: isDark 
                ? color.withValues(alpha: 0.25) 
                : color.withValues(alpha: 0.15),
            width: 1.0,
          ),
          boxShadow: [
            BoxShadow(
              color: color.withValues(alpha: isDark ? 0.08 : 0.03),
              blurRadius: 16,
              offset: const Offset(0, 8),
            )
          ],
        ),
        padding: const EdgeInsets.all(18.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.12),
                shape: BoxShape.circle,
              ),
              child: Icon(icon, color: color, size: 20),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w900,
                    color: isDark ? Colors.white : const Color(0xFF1E293B),
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: const TextStyle(fontSize: 10, color: Colors.grey),
                ),
              ],
            )
          ],
        ),
      ),
    );
  }

  // 构建未开放的次要功能 (灰化加密码锁)
  Widget _buildMinorTool(String title, IconData icon) {
    return AnimatedScaleButton(
      onTap: () {
        HapticFeedback.heavyImpact();
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('该模块正在合规升级中，暂未对当前岗位开放'), duration: Duration(milliseconds: 1200)),
        );
      },
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Stack(
            alignment: Alignment.bottomRight,
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.grey.withValues(alpha: 0.08),
                  shape: BoxShape.circle,
                ),
                child: Icon(icon, color: Colors.grey.shade400, size: 16),
              ),
              Container(
                decoration: const BoxDecoration(
                  color: Colors.redAccent,
                  shape: BoxShape.circle,
                ),
                padding: const EdgeInsets.all(2),
                child: const Icon(CupertinoIcons.lock, color: Colors.white, size: 8),
              )
            ],
          ),
          const SizedBox(height: 6),
          Text(
            title,
            style: const TextStyle(fontSize: 10, color: Colors.grey),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }

  // 渲染无权限占位视图
  Widget _buildNoPermissionView(String requiredRole) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: isDark 
              ? [const Color(0xFF090C15), const Color(0xFF0B1B2A), const Color(0xFF141221)]
              : [const Color(0xFFEAF6FF), Colors.white],
        ),
      ),
      child: Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(CupertinoIcons.lock, size: 64, color: Colors.red.withValues(alpha: 0.7)),
              const SizedBox(height: 16),
              const Text(
                '权限不足',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              Text(
                '该功能仅限 [$requiredRole] 角色的账户访问。',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.grey),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
