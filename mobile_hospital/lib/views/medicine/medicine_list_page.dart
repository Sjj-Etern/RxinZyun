import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'dart:ui';
import 'package:dio/dio.dart';
import 'package:provider/provider.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/data/models/medicine_model.dart';
import 'package:his_mobile/providers/auth_provider.dart';
import 'package:his_mobile/core/theme/glass_card.dart';
import 'package:his_mobile/core/widgets/animated_scale_button.dart';

class MedicineListPage extends StatefulWidget {
  const MedicineListPage({super.key});

  @override
  State<MedicineListPage> createState() => _MedicineListPageState();
}

class _MedicineListPageState extends State<MedicineListPage> {
  final List<MedicineModel> _medicines = [];
  bool _isLoading = false;
  String _keyword = '';
  final _searchController = TextEditingController();

  int _page = 1;
  int _total = 0;
  final int _pageSize = 15;

  // 展开功能状态
  int? _expandedMedicineId;
  final List<Map<String, dynamic>> _expandedTraceCodes = [];
  bool _isTraceLoading = false;
  final _newTraceCodeController = TextEditingController();

  @override
  void initState() {
    super.initState();
    _fetchMedicines(refresh: true);
  }

  @override
  void dispose() {
    _searchController.dispose();
    _newTraceCodeController.dispose();
    super.dispose();
  }

  Future<void> _fetchMedicines({bool refresh = false}) async {
    if (_isLoading) return;
    if (!refresh && _medicines.length >= _total) return;

    setState(() {
      _isLoading = true;
    });

    if (refresh) {
      _page = 1;
      _medicines.clear();
      _expandedMedicineId = null;
      _expandedTraceCodes.clear();
    }

    try {
      final response = await ApiClient().dio.get(
        '/api/medicines',
        queryParameters: {
          'page': _page,
          'pageSize': _pageSize,
          'keyword': _keyword,
        },
      );

      if (response.statusCode == 200) {
        final data = response.data;
        _total = data['total'] as int? ?? 0;
        final list = data['list'] as List? ?? [];

        setState(() {
          _medicines.addAll(list.map((m) => MedicineModel.fromJson(m as Map<String, dynamic>)));
          _page++;
        });
      }
    } on DioException catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('加载药品失败: ${e.message}')),
      );
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  void _handleSearch() {
    setState(() {
      _keyword = _searchController.text.trim();
    });
    _fetchMedicines(refresh: true);
  }

  // 展开药品卡片并获取其绑定的 20 位追溯码列表
  Future<void> _toggleExpand(int medicineId) async {
    if (_expandedMedicineId == medicineId) {
      setState(() {
        _expandedMedicineId = null;
        _expandedTraceCodes.clear();
      });
    } else {
      setState(() {
        _expandedMedicineId = medicineId;
        _expandedTraceCodes.clear();
        _isTraceLoading = true;
        _newTraceCodeController.clear();
      });
      await _fetchTraceCodes(medicineId);
    }
  }

  Future<void> _fetchTraceCodes(int medicineId) async {
    try {
      final response = await ApiClient().dio.get(
        '/api/medicine-trace-codes',
        queryParameters: {
          'medicine_id': medicineId,
          'page': 1,
          'pageSize': 50, // 取前 50 条测试追溯码
        },
      );
      if (response.statusCode == 200 && _expandedMedicineId == medicineId) {
        final list = response.data['list'] as List? ?? [];
        setState(() {
          _expandedTraceCodes.clear();
          _expandedTraceCodes.addAll(list.map((item) => item as Map<String, dynamic>));
        });
      }
    } catch (_) {}
    finally {
      if (mounted && _expandedMedicineId == medicineId) {
        setState(() {
          _isTraceLoading = false;
        });
      }
    }
  }

  // 网页端同款：手动添加 20 位追溯码
  Future<void> _handleAddTraceCode(int medicineId) async {
    final code = _newTraceCodeController.text.trim();
    if (code.isEmpty) return;
    if (code.length != 20) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('追溯码必须是 20 位数字')));
      return;
    }

    setState(() {
      _isTraceLoading = true;
    });

    try {
      final response = await ApiClient().dio.post(
        '/api/medicine-trace-codes',
        data: {
          'medicine_id': medicineId,
          'trace_code': code,
        },
      );
      if (response.statusCode == 201) {
        _newTraceCodeController.clear();
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('追溯码添加成功'), backgroundColor: Colors.green));
        await _fetchTraceCodes(medicineId);
      }
    } on DioException catch (e) {
      final err = e.response?.data?['error']?.toString() ?? '添加失败';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err), backgroundColor: Colors.redAccent));
    } finally {
      setState(() {
        _isTraceLoading = false;
      });
    }
  }

  // 网页端同款：模拟测试扫码流转
  Future<void> _handleTestScan(int tcId, int medicineId) async {
    try {
      final response = await ApiClient().dio.put('/api/medicine-trace-codes/$tcId/scan');
      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('流转扫码成功'), backgroundColor: Colors.green));
        await _fetchTraceCodes(medicineId);
      }
    } on DioException catch (e) {
      final err = e.response?.data?['error']?.toString() ?? '测试扫码失败';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err), backgroundColor: Colors.redAccent));
    }
  }

  // 网页端同款：撤销扫码流转
  Future<void> _handleTestUnscan(int tcId, int medicineId) async {
    try {
      final response = await ApiClient().dio.put('/api/medicine-trace-codes/$tcId/unscan');
      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('撤销扫码成功')));
        await _fetchTraceCodes(medicineId);
      }
    } on DioException catch (e) {
      final err = e.response?.data?['error']?.toString() ?? '撤销扫码失败';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err), backgroundColor: Colors.redAccent));
    }
  }

  // 网页端同款：删除单个追溯码
  Future<void> _handleDeleteTraceCode(int tcId, int medicineId) async {
    try {
      final response = await ApiClient().dio.delete('/api/medicine-trace-codes/$tcId');
      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('追溯码已删除')));
        await _fetchTraceCodes(medicineId);
      }
    } on DioException catch (e) {
      final err = e.response?.data?['error']?.toString() ?? '删除失败';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err), backgroundColor: Colors.redAccent));
    }
  }

  // 弹出修改前缀对话框 (Cupertino style)
  void _showPrefixDialog(MedicineModel medicine) {
    final controller = TextEditingController(text: medicine.traceCodePrefix ?? '');
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    showCupertinoDialog(
      context: context,
      builder: (context) {
        return CupertinoAlertDialog(
          title: Text('配置 [${medicine.name}] 7位前缀'),
          content: Material(
            color: Colors.transparent,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(height: 8),
                const Text('追溯码前缀必须是 7 位数字（例如：8422747），扫码时将根据此前缀匹配药品。', style: TextStyle(fontSize: 12, color: Colors.grey)),
                const SizedBox(height: 12),
                CupertinoTextField(
                  controller: controller,
                  keyboardType: TextInputType.number,
                  placeholder: '输入7位数字前缀',
                  style: TextStyle(color: isDark ? Colors.white : Colors.black87, fontSize: 13),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.02),
                    border: Border.all(color: isDark ? Colors.white12 : Colors.black12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
              ],
            ),
          ),
          actions: [
            CupertinoDialogAction(
              isDestructiveAction: true,
              onPressed: () {
                Navigator.pop(context);
                _updatePrefix(medicine.id, '');
              },
              child: const Text('删除前缀'),
            ),
            CupertinoDialogAction(
              onPressed: () => Navigator.pop(context),
              child: const Text('取消'),
            ),
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () {
                final prefix = controller.text.trim();
                if (prefix.isNotEmpty && !RegExp(r'^\d{7}$').hasMatch(prefix)) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('错误：前缀必须是7位数字')),
                  );
                  return;
                }
                Navigator.pop(context);
                _updatePrefix(medicine.id, prefix);
              },
              child: const Text('保存'),
            ),
          ],
        );
      },
    );
  }

  Future<void> _updatePrefix(int medicineId, String prefix) async {
    setState(() {
      _isLoading = true;
    });

    try {
      Response response;
      if (prefix.isEmpty) {
        response = await ApiClient().dio.delete('/api/medicines/$medicineId/prefix');
      } else {
        response = await ApiClient().dio.put(
          '/api/medicines/$medicineId/prefix',
          data: {'prefix': prefix},
        );
      }

      if (response.statusCode == 200) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('追溯码前缀配置已更新'), backgroundColor: Colors.green),
        );
        _fetchMedicines(refresh: true);
      }
    } on DioException catch (e) {
      final err = e.response?.data?['error']?.toString() ?? '配置更新失败';
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err), backgroundColor: Colors.redAccent));
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  String _getTraceStatusText(String status) {
    switch (status) {
      case 'pending': return '待扫描';
      case 'scanned_identify': return '已识别';
      case 'scanned_outbound': return '已出库';
      case 'scanned_confirm': return '已确认';
      default: return '未知';
    }
  }

  Color _getTraceStatusColor(String status) {
    switch (status) {
      case 'pending': return Colors.orange;
      case 'scanned_identify': return Colors.blue;
      case 'scanned_outbound': return Colors.purple;
      case 'scanned_confirm': return Colors.green;
      default: return Colors.grey;
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
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final isPharmacist = context.read<AuthProvider>().currentUser?.isPharmacist ?? false;

    return Scaffold(
      appBar: AppBar(
        title: const Text('药品及追溯码管理'),
        backgroundColor: Colors.transparent,
        elevation: 0,
      ),
      body: Stack(
        children: [
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
            child: Column(
              children: [
            // 苹果极简圆角搜索栏
            Padding(
              padding: const EdgeInsets.fromLTRB(20.0, 12.0, 20.0, 8.0),
              child: Row(
                children: [
                  Expanded(
                    child: Container(
                      decoration: BoxDecoration(
                        color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.04),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      child: TextField(
                        controller: _searchController,
                        style: TextStyle(color: isDark ? Colors.white : Colors.black87),
                        decoration: InputDecoration(
                          border: InputBorder.none,
                          filled: false,
                          enabledBorder: InputBorder.none,
                          focusedBorder: InputBorder.none,
                          errorBorder: InputBorder.none,
                          focusedErrorBorder: InputBorder.none,
                          hintText: '搜索药品名称或制造厂商',
                          hintStyle: const TextStyle(fontSize: 12, color: Colors.grey),
                          prefixIcon: Icon(CupertinoIcons.search, size: 18, color: isDark ? Colors.white60 : Colors.black45),
                          suffixIcon: _searchController.text.isNotEmpty
                              ? IconButton(
                                  icon: Icon(CupertinoIcons.clear_circled_solid, size: 16, color: isDark ? Colors.white60 : Colors.black45),
                                  onPressed: () {
                                    _searchController.clear();
                                    _handleSearch();
                                  },
                                )
                              : null,
                        ),
                        onSubmitted: (_) => _handleSearch(),
                        onChanged: (val) {
                          setState(() {});
                        },
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  AnimatedScaleButton(
                    onTap: _handleSearch,
                    child: Container(
                      height: 48,
                      padding: const EdgeInsets.symmetric(horizontal: 20),
                      decoration: BoxDecoration(
                        gradient: const LinearGradient(
                          colors: [Color(0xFF009688), Color(0xFF00796B)],
                        ),
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: [
                          BoxShadow(
                            color: const Color(0xFF009688).withValues(alpha: 0.2),
                            blurRadius: 8,
                            offset: const Offset(0, 4),
                          )
                        ],
                      ),
                      alignment: Alignment.center,
                      child: const Text(
                        '搜索',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 13, letterSpacing: 1.0),
                      ),
                    ),
                  ),
                ],
              ),
            ),

            // 药品列表
            Expanded(
              child: RefreshIndicator(
                onRefresh: () => _fetchMedicines(refresh: true),
                color: const Color(0xFF00796B),
                child: _medicines.isEmpty && !_isLoading
                    ? ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        children: const [
                          Padding(
                            padding: EdgeInsets.symmetric(vertical: 120.0),
                            child: Center(child: Text('无药品库存数据', style: TextStyle(color: Colors.grey, fontSize: 14))),
                          ),
                        ],
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.fromLTRB(20.0, 12.0, 20.0, 110.0), // 留底给悬浮底栏
                        itemCount: _medicines.length + (_isLoading ? 1 : 0),
                        itemBuilder: (context, index) {
                          if (index == _medicines.length) {
                            return const Padding(
                              padding: EdgeInsets.symmetric(vertical: 20.0),
                              child: Center(child: CircularProgressIndicator(color: Color(0xFF00796B))),
                            );
                          }

                          final medicine = _medicines[index];
                          final isExpanded = _expandedMedicineId == medicine.id;

                          return Padding(
                            padding: const EdgeInsets.only(bottom: 16.0),
                            child: GlassCard(
                              margin: EdgeInsets.zero,
                              padding: const EdgeInsets.all(20.0),
                              borderRadius: 24,
                              child: AnimatedSize(
                                duration: const Duration(milliseconds: 250),
                                curve: Curves.easeInOut,
                                child: InkWell(
                                  onTap: () => _toggleExpand(medicine.id),
                                  borderRadius: BorderRadius.circular(20),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Expanded(
                                            child: Text(
                                              medicine.name,
                                              style: TextStyle(
                                                fontWeight: FontWeight.w900, 
                                                fontSize: 16,
                                                color: isDark ? Colors.white : const Color(0xFF1E293B),
                                              ),
                                            ),
                                          ),
                                          if (medicine.isNarcoticBool)
                                            Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                              decoration: BoxDecoration(
                                                color: Colors.redAccent.withValues(alpha: 0.12),
                                                borderRadius: BorderRadius.circular(8),
                                              ),
                                              child: const Text(
                                                '麻精药品',
                                                style: TextStyle(color: Colors.redAccent, fontSize: 9, fontWeight: FontWeight.bold),
                                              ),
                                            ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      if (medicine.genericName != null && medicine.genericName != medicine.name)
                                        Padding(
                                          padding: const EdgeInsets.only(bottom: 4.0),
                                          child: Text('通用名: ${medicine.genericName}', style: const TextStyle(color: Colors.grey, fontSize: 13)),
                                        ),
                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text('规格: ${medicine.specification ?? "无"}', style: const TextStyle(fontSize: 13, color: Colors.grey)),
                                          Text('价格: ¥${medicine.price.toStringAsFixed(2)} / ${medicine.unit}', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: isDark ? Colors.white : const Color(0xFF0F172A))),
                                        ],
                                      ),
                                      const SizedBox(height: 6),
                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Expanded(child: Text('厂商: ${medicine.manufacturer ?? "未知"}', style: const TextStyle(fontSize: 12, color: Colors.grey), maxLines: 1, overflow: TextOverflow.ellipsis)),
                                          Row(
                                            children: [
                                              const Text('库存: ', style: TextStyle(fontSize: 13, color: Colors.grey)),
                                              Text(
                                                '${medicine.stock}',
                                                style: TextStyle(
                                                  fontWeight: FontWeight.w900,
                                                  fontSize: 14,
                                                  color: medicine.stock < 10 ? Colors.red : Colors.green,
                                                ),
                                              ),
                                            ],
                                          )
                                        ],
                                      ),
                                      const Divider(height: 24, color: Colors.black12),
                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text(
                                            medicine.traceCodePrefix != null 
                                                ? '前缀: ${medicine.traceCodePrefix}' 
                                                : '前缀: 未配置',
                                            style: TextStyle(
                                              fontSize: 12,
                                              color: medicine.traceCodePrefix != null ? const Color(0xFF00796B) : Colors.orange,
                                              fontWeight: FontWeight.w800,
                                            ),
                                          ),
                                          Text(
                                            isExpanded ? '收起详情 ▴' : '展开追溯码 ▾',
                                            style: const TextStyle(fontSize: 11, color: Color(0xFF00796B), fontWeight: FontWeight.bold),
                                          )
                                        ],
                                      ),

                                      // 展开显示 20 位追溯码 CRUD 控制面板
                                      if (isExpanded) ...[
                                        const Divider(height: 24, color: Colors.black12),
                                        // 1. 修改前缀选项 (仅药师可用)
                                        if (isPharmacist) ...[
                                          Row(
                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                            children: [
                                              const Text('前缀维护 (7位):', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w800)),
                                              CupertinoButton(
                                                onPressed: () => _showPrefixDialog(medicine),
                                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                                                color: const Color(0xFF00796B).withValues(alpha: 0.1),
                                                borderRadius: BorderRadius.circular(10),
                                                minimumSize: Size.zero,
                                                child: Row(
                                                  children: const [
                                                    Icon(CupertinoIcons.settings, size: 13, color: Color(0xFF00796B)),
                                                    SizedBox(width: 4),
                                                    Text('修改前缀', style: TextStyle(fontSize: 11, color: Color(0xFF00796B), fontWeight: FontWeight.bold)),
                                                  ],
                                                ),
                                              ),
                                            ],
                                          ),
                                          const SizedBox(height: 12),
                                        ],
                                        // 2. 添加追溯码表单 (仅药师可用)
                                        if (isPharmacist) ...[
                                          Row(
                                            children: [
                                              Expanded(
                                                child: Container(
                                                  decoration: BoxDecoration(
                                                    color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.02),
                                                    borderRadius: BorderRadius.circular(12),
                                                  ),
                                                  padding: const EdgeInsets.symmetric(horizontal: 12),
                                                  child: TextField(
                                                    controller: _newTraceCodeController,
                                                    keyboardType: TextInputType.number,
                                                    style: const TextStyle(fontSize: 13),
                                                    decoration: const InputDecoration(
                                                      hintText: '输入20位全新追溯码',
                                                      hintStyle: TextStyle(fontSize: 12, color: Colors.grey),
                                                      border: InputBorder.none,
                                                      filled: false,
                                                      enabledBorder: InputBorder.none,
                                                      focusedBorder: InputBorder.none,
                                                      errorBorder: InputBorder.none,
                                                      focusedErrorBorder: InputBorder.none,
                                                      isDense: true,
                                                      contentPadding: EdgeInsets.symmetric(vertical: 8),
                                                    ),
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(width: 8),
                                              AnimatedScaleButton(
                                                onTap: () => _handleAddTraceCode(medicine.id),
                                                child: Container(
                                                  height: 38,
                                                  padding: const EdgeInsets.symmetric(horizontal: 16),
                                                  decoration: BoxDecoration(
                                                    color: const Color(0xFF00796B),
                                                    borderRadius: BorderRadius.circular(12),
                                                  ),
                                                  alignment: Alignment.center,
                                                  child: const Text('添加', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 12)),
                                                ),
                                              ),
                                            ],
                                          ),
                                          const SizedBox(height: 16),
                                        ],
                                        // 3. 追溯码子列表
                                        const Text('已绑定追溯码列表:', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w800)),
                                        const SizedBox(height: 8),
                                        _isTraceLoading
                                            ? const Center(
                                                child: Padding(
                                                  padding: EdgeInsets.all(12.0),
                                                  child: CircularProgressIndicator(color: Color(0xFF00796B)),
                                                ),
                                              )
                                            : _expandedTraceCodes.isEmpty
                                                ? const Padding(
                                                    padding: EdgeInsets.symmetric(vertical: 12.0),
                                                    child: Text('无追溯码记录，请在上方录入。', style: TextStyle(color: Colors.grey, fontSize: 12)),
                                                  )
                                                : ListView.builder(
                                                    shrinkWrap: true,
                                                    physics: const NeverScrollableScrollPhysics(),
                                                    itemCount: _expandedTraceCodes.length,
                                                    itemBuilder: (context, idx) {
                                                      final tc = _expandedTraceCodes[idx];
                                                      final tcId = tc['id'] as int;
                                                      final traceCode = tc['trace_code'] as String;
                                                      final status = tc['status'] as String? ?? 'pending';

                                                      return Container(
                                                        margin: const EdgeInsets.symmetric(vertical: 6),
                                                        padding: const EdgeInsets.all(12),
                                                        decoration: BoxDecoration(
                                                          color: isDark ? Colors.white.withValues(alpha: 0.04) : Colors.white.withValues(alpha: 0.5),
                                                          borderRadius: BorderRadius.circular(12),
                                                          border: Border.all(color: isDark ? Colors.white10 : Colors.black12),
                                                        ),
                                                        child: Column(
                                                          crossAxisAlignment: CrossAxisAlignment.start,
                                                          children: [
                                                            Row(
                                                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                                              children: [
                                                                Expanded(
                                                                  child: SelectableText(
                                                                    traceCode,
                                                                    style: TextStyle(
                                                                      fontFamily: 'monospace',
                                                                      fontSize: 12,
                                                                      fontWeight: FontWeight.w800,
                                                                      color: isDark ? Colors.white70 : const Color(0xFF1E293B),
                                                                    ),
                                                                  ),
                                                                ),
                                                                Container(
                                                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                                                  decoration: BoxDecoration(
                                                                    color: _getTraceStatusColor(status).withValues(alpha: 0.12),
                                                                    borderRadius: BorderRadius.circular(6),
                                                                  ),
                                                                  child: Text(
                                                                    _getTraceStatusText(status),
                                                                    style: TextStyle(
                                                                      color: _getTraceStatusColor(status),
                                                                      fontSize: 9,
                                                                      fontWeight: FontWeight.bold,
                                                                    ),
                                                                  ),
                                                                ),
                                                              ],
                                                            ),
                                                            // 网页端测试按钮
                                                            if (isPharmacist) ...[
                                                              const SizedBox(height: 8),
                                                              Row(
                                                                mainAxisAlignment: MainAxisAlignment.end,
                                                                children: [
                                                                  TextButton.icon(
                                                                    onPressed: () => _handleTestScan(tcId, medicine.id),
                                                                    icon: const Icon(CupertinoIcons.play_arrow_solid, size: 12, color: Colors.green),
                                                                    label: const Text('模拟扫描', style: TextStyle(fontSize: 11, color: Colors.green, fontWeight: FontWeight.bold)),
                                                                    style: TextButton.styleFrom(minimumSize: Size.zero, padding: const EdgeInsets.symmetric(horizontal: 8)),
                                                                  ),
                                                                  const SizedBox(width: 8),
                                                                  TextButton.icon(
                                                                    onPressed: () => _handleTestUnscan(tcId, medicine.id),
                                                                    icon: const Icon(CupertinoIcons.reply, size: 12, color: Colors.orange),
                                                                    label: const Text('撤销', style: TextStyle(fontSize: 11, color: Colors.orange, fontWeight: FontWeight.bold)),
                                                                    style: TextButton.styleFrom(minimumSize: Size.zero, padding: const EdgeInsets.symmetric(horizontal: 8)),
                                                                  ),
                                                                  const SizedBox(width: 8),
                                                                  TextButton.icon(
                                                                    onPressed: () => _handleDeleteTraceCode(tcId, medicine.id),
                                                                    icon: const Icon(CupertinoIcons.trash, size: 12, color: Colors.red),
                                                                    label: const Text('删除', style: TextStyle(fontSize: 11, color: Colors.red, fontWeight: FontWeight.bold)),
                                                                    style: TextButton.styleFrom(minimumSize: Size.zero, padding: const EdgeInsets.symmetric(horizontal: 8)),
                                                                  ),
                                                                ],
                                                              ),
                                                            ],
                                                          ],
                                                        ),
                                                      );
                                                    },
                                                  ),
                                      ],
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          );
                        },
                      ),
              ),
            ),
          ],
        ),
      ),
    ],
  ),
    );
  }
}
