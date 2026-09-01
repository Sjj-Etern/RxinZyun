import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/cupertino.dart';
import 'dart:ui';
import 'package:dio/dio.dart';
import 'package:provider/provider.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/data/models/prescription_model.dart';
import 'package:his_mobile/providers/auth_provider.dart';
import 'package:his_mobile/core/theme/glass_card.dart';
import 'package:his_mobile/core/widgets/animated_scale_button.dart';
import 'scanner_page.dart';

class PrescriptionDetailPage extends StatefulWidget {
  final int prescriptionId;

  const PrescriptionDetailPage({super.key, required this.prescriptionId});

  @override
  State<PrescriptionDetailPage> createState() => _PrescriptionDetailPageState();
}

class _PrescriptionDetailPageState extends State<PrescriptionDetailPage> {
  PrescriptionModel? _prescription;
  bool _isLoading = false;

  // 顶部胶囊悬浮弹窗（AirPods 动态岛风格）
  String? _floatingAlertMessage;
  bool _floatingAlertSuccess = true;

  @override
  void initState() {
    super.initState();
    _fetchDetails();
  }

  void _showFloatingAlert(String msg, bool success) {
    HapticFeedback.mediumImpact();
    setState(() {
      _floatingAlertMessage = msg;
      _floatingAlertSuccess = success;
    });
    Future.delayed(const Duration(milliseconds: 2500), () {
      if (mounted) {
        setState(() {
          _floatingAlertMessage = null;
        });
      }
    });
  }

  Future<void> _fetchDetails() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final response = await ApiClient().dio.get('/api/prescriptions/${widget.prescriptionId}');
      if (response.statusCode == 200 && mounted) {
        setState(() {
          _prescription = PrescriptionModel.fromJson(response.data as Map<String, dynamic>);
        });
      }
    } on DioException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('获取详情失败: ${e.message}')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  // 确认发药并选择机器人
  Future<void> _handleDispense() async {
    try {
      final robotResponse = await ApiClient().dio.get('/api/robots');
      final robots = (robotResponse.data as List)
          .where((robot) => robot['status'] == 'available')
          .toList();
      if (!mounted) return;
      if (robots.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('暂无空闲配送机器人')),
        );
        return;
      }
      final robotId = await showDialog<int>(
        context: context,
        builder: (dialogContext) => SimpleDialog(
          title: const Text('选择配送机器人'),
          children: robots.map((robot) => SimpleDialogOption(
            onPressed: () => Navigator.pop(dialogContext, robot['id'] as int),
            child: Text('${robot['code']} · ${robot['name']}'),
          )).toList(),
        ),
      );
      if (robotId == null) return;

      setState(() {
        _isLoading = true;
      });
      final response = await ApiClient().dio.put(
        '/api/prescriptions/${widget.prescriptionId}/dispense',
        data: {'robot_id': robotId},
      );
      if (response.statusCode == 200 && mounted) {
        _showFloatingAlert(response.data['message'] ?? '机器人已开始配送', true);
        _fetchDetails();
      }
    } on DioException catch (e) {
      final err = e.response?.data?['error']?.toString() ?? '确认配送失败';
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(err), backgroundColor: Colors.redAccent),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }
  // 触发相机扫码复核追溯码
  Future<void> _handleScanCode() async {
    final scannedCode = await Navigator.push<String>(
      context,
      MaterialPageRoute(builder: (context) => const ScannerPage()),
    );

    if (scannedCode != null && scannedCode.isNotEmpty) {
      await _processScannedCode(scannedCode);
    }
  }

  Future<void> _processScannedCode(String code) async {
    setState(() {
      _isLoading = true;
    });

    try {
      final response = await ApiClient().dio.post(
        '/api/medicine-trace-codes/scan-by-code',
        data: {'trace_code': code},
      );

      if (response.statusCode == 200 && mounted) {
        final data = response.data;
        final actionName = data['action']?.toString() ?? '推进';
        final isCompleted = data['completed'] as bool? ?? false;
        final medicineName = data['medicine_name']?.toString() ?? '药品';

        // 顶层悬浮动态岛弹窗展示结果，无需阻塞式弹窗
        _showFloatingAlert(
          '[$medicineName] $actionName成功！${isCompleted ? "已完成复合验证" : ""}',
          true,
        );
        
        _fetchDetails();
      }
    } on DioException catch (e) {
      HapticFeedback.heavyImpact(); // 失败强震动
      final err = e.response?.data?['error']?.toString() ?? '药品追溯码校验失败';
      _showFloatingAlert(err, false);
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  // 判断是否已完成所有的追溯码扫描
  bool get _allScanned {
    if (_prescription == null || _prescription!.items.isEmpty) return false;
    return _prescription!.items.every((item) => item.traceStatus == 'scanned_confirm');
  }

  @override
  Widget build(BuildContext context) {
    if (_prescription == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('处方详情')),
        body: const Center(child: CircularProgressIndicator(color: Color(0xFF009688))),
      );
    }

    final p = _prescription!;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final isPharmacist = context.read<AuthProvider>().currentUser?.isPharmacist ?? false;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: Text(
          '门诊号: ${p.prescriptionCode}',
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          if (isPharmacist && (p.status == 'approved' || p.status == 'dispensing'))
            IconButton(
              icon: const Icon(CupertinoIcons.barcode_viewfinder, color: Color(0xFF009688), size: 26),
              onPressed: _handleScanCode,
              tooltip: '扫码出库追溯',
            )
        ],
      ),
      body: Stack(
        children: [
          // 全局高奢三色极光渐变背景
          Positioned.fill(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
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
            child: _isLoading
                ? const Center(child: CircularProgressIndicator(color: Color(0xFF009688)))
                : SafeArea(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.fromLTRB(20.0, 12.0, 20.0, 120.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // 1. 顶部状态大看板 (Cupertino Status Header)
                          _buildStatusHeader(p, isDark),
                          const SizedBox(height: 16),

                          // 2. 患者档案与就诊网格 (Grid Info Layout)
                          _buildPatientGrid(p, isDark),
                          const SizedBox(height: 16),

                          // 3. 药品大卡片与流转时序图
                          const Padding(
                            padding: EdgeInsets.symmetric(horizontal: 4.0, vertical: 8.0),
                            child: Text(
                              '开具药品及追溯码流转时序',
                              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w900, color: Colors.grey),
                            ),
                          ),
                          ...List.generate(p.items.length, (index) {
                            final item = p.items[index];
                            return _buildMedicineCard(item, isDark);
                          }),
                          const SizedBox(height: 24),

                          // 4. 发药操作面板
                          if (isPharmacist) ...[
                            // 待发药 -> 扫码出库 / 确认发药
                            if (p.status == 'approved' || p.status == 'dispensing')
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  AnimatedScaleButton(
                                    onTap: _handleScanCode,
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(vertical: 16),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFF009688),
                                        borderRadius: BorderRadius.circular(16),
                                        boxShadow: [
                                          BoxShadow(
                                            color: const Color(0xFF009688).withValues(alpha: 0.2),
                                            blurRadius: 8,
                                            offset: const Offset(0, 4),
                                          )
                                        ],
                                      ),
                                      child: const Row(
                                        mainAxisAlignment: MainAxisAlignment.center,
                                        children: [
                                          Icon(CupertinoIcons.barcode_viewfinder, color: Colors.white, size: 20),
                                          SizedBox(width: 8),
                                          Text('扫码出库追溯', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 15)),
                                        ],
                                      ),
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  AnimatedScaleButton(
                                    onTap: _handleDispense,
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(vertical: 16),
                                      decoration: BoxDecoration(
                                        color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.03),
                                        borderRadius: BorderRadius.circular(16),
                                        border: Border.all(
                                          color: isDark ? Colors.white24 : Colors.black12,
                                          width: 1,
                                        ),
                                      ),
                                      child: Center(
                                        child: Text(
                                          _allScanned ? '确认发药' : '直接确认发药(跳过扫码)',
                                          style: TextStyle(
                                            color: _allScanned 
                                                ? (isDark ? const Color(0xFF4DB6AC) : const Color(0xFF00796B))
                                                : (isDark ? Colors.white70 : Colors.black87),
                                            fontWeight: FontWeight.w800,
                                            fontSize: 14,
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                          ],
                        ],
                      ),
                    ),
                  ),
          ),

          // 5. AirPods 风格顶部胶囊悬浮弹窗 (Dynamic Island style overlay)
          if (_floatingAlertMessage != null)
            Positioned(
              top: MediaQuery.of(context).padding.top + 10,
              left: 20,
              right: 20,
              child: _SlidingCapsule(
                message: _floatingAlertMessage!,
                isSuccess: _floatingAlertSuccess,
              ),
            ),
        ],
      ),
    );
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

  // 顶部状态大看板组件
  Widget _buildStatusHeader(PrescriptionModel p, bool isDark) {
    Color stateColor;
    String stateTitle;
    String stateDesc;

    switch (p.status) {
      case 'pending':
        stateColor = const Color(0xFFFF9F0A);
        stateTitle = '待发药';
        stateDesc = '处方已进入发药队列，请扫码出库或确认发药';
        break;
      case 'approved':
      case 'dispensing':
        stateColor = const Color(0xFF30D158);
        stateTitle = '待发药';
        stateDesc = '处方已进入发药环节，请扫码出库或确认发药';
        break;
      case 'dispensed':
        stateColor = const Color(0xFF0A84FF);
        stateTitle = '药品已发放';
        stateDesc = '处方已核对确认，完成物理药盒发放';
        break;
      case 'rejected':
        stateColor = const Color(0xFFFF453A);
        stateTitle = '处方已被驳回';
        stateDesc = '审核未通过，请检查医生留言说明';
        break;
      default:
        stateColor = Colors.grey;
        stateTitle = p.statusText;
        stateDesc = '未知流转状态';
    }

    return GlassCard(
      margin: EdgeInsets.zero,
      padding: const EdgeInsets.all(20.0),
      borderRadius: 24,
      child: Row(
        children: [
          _PulseDot(color: stateColor),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  stateTitle,
                  style: TextStyle(
                    fontSize: 18, 
                    fontWeight: FontWeight.w900,
                    color: isDark ? Colors.white : const Color(0xFF1E293B),
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  stateDesc,
                  style: const TextStyle(fontSize: 12, color: Colors.grey, height: 1.3),
                ),
              ],
            ),
          )
        ],
      ),
    );
  }

  // 患者就诊双列网格档案组件
  Widget _buildPatientGrid(PrescriptionModel p, bool isDark) {
    final note = p.items.isNotEmpty ? p.items.first.note : null;

    return GlassCard(
      margin: EdgeInsets.zero,
      padding: const EdgeInsets.all(20.0),
      borderRadius: 24,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 20,
                backgroundColor: p.patientGender == '男' 
                    ? const Color(0xFF007AFF).withValues(alpha: 0.1) 
                    : const Color(0xFFFF2D55).withValues(alpha: 0.1),
                child: Icon(
                  CupertinoIcons.person_solid,
                  color: p.patientGender == '男' ? const Color(0xFF007AFF) : const Color(0xFFFF2D55),
                  size: 18,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${p.patientName ?? "未知"} (${p.patientGender ?? "未知"} · ${p.patientAge ?? 0}岁)',
                      style: TextStyle(
                        fontWeight: FontWeight.w900, 
                        fontSize: 17,
                        color: isDark ? Colors.white : const Color(0xFF1E293B),
                      ),
                    ),
                    const SizedBox(height: 2),
                    const Text('就诊科别: 全科内门诊(三楼)', style: TextStyle(fontSize: 11, color: Colors.grey)),
                  ],
                ),
              )
            ],
          ),
          const Divider(height: 24, color: Colors.black12),
          
          // 双列磁贴网格布局，去AI感排版
          Row(
            children: [
              Expanded(
                child: _buildGridItem(
                  icon: CupertinoIcons.doc_plaintext,
                  label: '病历号',
                  value: p.prescriptionCode.substring(p.prescriptionCode.length > 6 ? p.prescriptionCode.length - 6 : 0),
                  isDark: isDark,
                ),
              ),
              Expanded(
                child: _buildGridItem(
                  icon: CupertinoIcons.bed_double_fill,
                  label: '床位号',
                  value: '门诊号',
                  isDark: isDark,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _buildGridItem(
                  icon: CupertinoIcons.money_yen_circle,
                  label: '费别类型',
                  value: '自费/医保',
                  isDark: isDark,
                ),
              ),
              Expanded(
                child: _buildGridItem(
                  icon: CupertinoIcons.doc_text,
                  label: '处方类别',
                  value: '普通门诊',
                  isDark: isDark,
                ),
              ),
            ],
          ),
          
          if (note?.isNotEmpty == true) ...[
            const Divider(height: 24, color: Colors.black12),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(CupertinoIcons.chat_bubble_text_fill, color: Colors.grey, size: 14),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '医生说明: $note',
                    style: const TextStyle(fontSize: 12, color: Colors.grey, height: 1.3),
                  ),
                ),
              ],
            ),
          ]
        ],
      ),
    );
  }

  Widget _buildGridItem({
    required IconData icon, 
    required String label, 
    required String value,
    required bool isDark,
  }) {
    return Row(
      children: [
        Icon(icon, size: 14, color: isDark ? Colors.white60 : Colors.black45),
        const SizedBox(width: 8),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: const TextStyle(fontSize: 10, color: Colors.grey)),
            const SizedBox(height: 2),
            Text(
              value, 
              style: TextStyle(
                fontSize: 13, 
                fontWeight: FontWeight.bold,
                color: isDark ? Colors.white : const Color(0xFF1E293B),
              ),
            ),
          ],
        )
      ],
    );
  }

  // 药品明细微画报卡片组件
  Widget _buildMedicineCard(PrescriptionItemModel item, bool isDark) {
    return GlassCard(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(20.0),
      borderRadius: 24,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 药品头与数量角标
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Text(
                  item.medicineName ?? '未知药品',
                  style: TextStyle(
                    fontWeight: FontWeight.w900, 
                    fontSize: 16,
                    color: isDark ? Colors.white : const Color(0xFF1E293B),
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: (isDark ? Colors.white : Colors.black).withValues(alpha: 0.06),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Text(
                  'x${item.quantity} ${item.unit ?? "盒"}',
                  style: TextStyle(
                    fontWeight: FontWeight.bold, 
                    fontSize: 12,
                    color: isDark ? Colors.white70 : Colors.black87,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          // 厂商与用法说明
          Text(
            '规格: ${item.specification ?? "无"} | 厂商: ${item.manufacturer ?? "未知"}',
            style: const TextStyle(color: Colors.grey, fontSize: 11),
          ),
          Text(
            '用法: ${item.usageMethod ?? "口服"} · ${item.dosage ?? "1次/天"} · 频次: ${item.frequency ?? "每日3次"}',
            style: const TextStyle(color: Colors.grey, fontSize: 11),
          ),
          const Divider(height: 24, color: Colors.black12),

          // 核心：药品流转时序进度条 (Custom Timeline)
          _buildTimeline(item.traceStatus),
          const SizedBox(height: 12),

          // 底部追溯码详细信息
          Row(
            children: [
              const Icon(CupertinoIcons.qrcode, color: Colors.grey, size: 12),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  '追溯码: ${item.traceCode ?? "未绑定追溯码数据"}',
                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  // 药品时序进度条组件
  Widget _buildTimeline(String? traceStatus) {
    // 阶段名称列表
    final stages = [
      {'key': 'pending', 'label': '待扫描'},
      {'key': 'scanned_identify', 'label': '已识别'},
      {'key': 'scanned_outbound', 'label': '已出库'},
      {'key': 'scanned_confirm', 'label': '已确认'},
    ];

    int activeIndex = 0;
    if (traceStatus == 'scanned_identify') {
      activeIndex = 1;
    } else if (traceStatus == 'scanned_outbound') {
      activeIndex = 2;
    } else if (traceStatus == 'scanned_confirm') {
      activeIndex = 3;
    }

    return Row(
      children: List.generate(stages.length, (idx) {
        final stage = stages[idx];
        final isCompleted = idx < activeIndex;
        final isActive = idx == activeIndex && traceStatus != null;

        Color dotColor;
        Widget dotChild;

        if (isCompleted) {
          dotColor = const Color(0xFF30D158); // Apple green
          dotChild = const Icon(CupertinoIcons.checkmark, size: 10, color: Colors.white);
        } else if (isActive) {
          dotColor = const Color(0xFF007AFF); // Apple blue
          dotChild = const _PulseDot(color: Color(0xFF007AFF));
        } else {
          dotColor = Colors.grey.shade400;
          dotChild = Container(
            width: 6, 
            height: 6, 
            decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.white),
          );
        }

        return Expanded(
          child: Row(
            children: [
              // 节点 Dot 与说明文字
              Column(
                children: [
                  Container(
                    width: 18,
                    height: 18,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: dotColor,
                    ),
                    child: Center(child: dotChild),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    stage['label']!,
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: isActive ? FontWeight.w800 : FontWeight.normal,
                      color: isActive 
                          ? const Color(0xFF007AFF) 
                          : (isCompleted ? const Color(0xFF30D158) : Colors.grey),
                    ),
                  ),
                ],
              ),
              // 两个点之间的流体连接线 (最后一个点后面不绘制线)
              if (idx < stages.length - 1)
                Expanded(
                  child: Container(
                    height: 2,
                    margin: const EdgeInsets.only(bottom: 16), // 与圆圈圆心保持纵向对齐
                    color: isCompleted ? const Color(0xFF30D158) : Colors.grey.shade300,
                  ),
                ),
            ],
          ),
        );
      }),
    );
  }
}

// 柔和微气泡呼吸灯组件
class _PulseDot extends StatefulWidget {
  final Color color;
  const _PulseDot({required this.color});

  @override
  State<_PulseDot> createState() => _PulseDotState();
}

class _PulseDotState extends State<_PulseDot> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1550),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        return Stack(
          alignment: Alignment.center,
          children: [
            Container(
              width: 10 + (16 * _controller.value),
              height: 10 + (16 * _controller.value),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: widget.color.withValues(alpha: 0.4 * (1.0 - _controller.value)),
              ),
            ),
            Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: widget.color,
              ),
            ),
          ],
        );
      },
    );
  }
}

// AirPods 风格顶部胶囊悬浮弹窗
class _SlidingCapsule extends StatefulWidget {
  final String message;
  final bool isSuccess;
  const _SlidingCapsule({required this.message, required this.isSuccess});

  @override
  State<_SlidingCapsule> createState() => _SlidingCapsuleState();
}

class _SlidingCapsuleState extends State<_SlidingCapsule> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<Offset> _offsetAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 350),
    );
    _offsetAnimation = Tween<Offset>(
      begin: const Offset(0.0, -1.8),
      end: Offset.zero,
    ).animate(CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOutBack, // 具有阻尼惯性反弹的高级曲线
    ));
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SlideTransition(
      position: _offsetAnimation,
      child: Center(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
          decoration: BoxDecoration(
            color: widget.isSuccess 
                ? const Color(0xFF10B981).withValues(alpha: 0.95) 
                : Colors.redAccent.withValues(alpha: 0.95),
            borderRadius: BorderRadius.circular(30),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.15),
                blurRadius: 16,
                offset: const Offset(0, 8),
              )
            ],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                widget.isSuccess ? CupertinoIcons.checkmark_circle_fill : CupertinoIcons.clear_circled_solid,
                color: Colors.white,
                size: 20,
              ),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  widget.message,
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 13),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
