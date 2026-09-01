import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/cupertino.dart';
import 'dart:ui';
import 'package:dio/dio.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/data/models/prescription_model.dart';
import 'prescription_detail_page.dart';
import 'scanner_page.dart';
import 'package:his_mobile/core/theme/glass_card.dart';
import 'package:his_mobile/core/widgets/animated_scale_button.dart';

class PrescriptionListPage extends StatefulWidget {
  const PrescriptionListPage({super.key});

  @override
  State<PrescriptionListPage> createState() => _PrescriptionListPageState();
}

class _PrescriptionListPageState extends State<PrescriptionListPage> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final List<PrescriptionModel> _prescriptions = [];
  bool _isLoading = false;

  int _page = 1;
  int _total = 0;
  final int _pageSize = 10;
  String _selectedStatus = 'pending'; // 默认待审核

  // 映射 Tab 索引到 API 的 status 值
  final List<Map<String, String>> _tabs = [
    {'title': '待审核', 'status': 'pending'},
    {'title': '待配药', 'status': 'approved'},
    {'title': '配药中', 'status': 'dispensing'},
    {'title': '已完成', 'status': 'completed'},
    {'title': '已驳回', 'status': 'rejected'},
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: _tabs.length, vsync: this);
    _tabController.addListener(() {
      if (!_tabController.indexIsChanging) {
        setState(() {
          _selectedStatus = _tabs[_tabController.index]['status']!;
        });
        _fetchPrescriptions(refresh: true);
      }
    });
    _fetchPrescriptions(refresh: true);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _fetchPrescriptions({bool refresh = false}) async {
    if (_isLoading) return;
    if (!refresh && _prescriptions.length >= _total) return;

    setState(() {
      _isLoading = true;
    });

    if (refresh) {
      _page = 1;
      _prescriptions.clear();
    }

    try {
      final response = await ApiClient().dio.get(
        '/api/prescriptions',
        queryParameters: {
          'page': _page,
          'pageSize': _pageSize,
          'status': _selectedStatus,
        },
      );

      if (response.statusCode == 200) {
        final data = response.data;
        _total = data['total'] as int? ?? 0;
        final list = data['list'] as List? ?? [];

        setState(() {
          _prescriptions.addAll(list.map((p) => PrescriptionModel.fromJson(p as Map<String, dynamic>)));
          _page++;
        });
      }
    } on DioException catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('加载处方列表失败: ${e.message}')),
      );
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case 'pending':
        return Colors.orange;
      case 'approved':
        return Colors.blue;
      case 'dispensing':
        return Colors.purple;
      case 'completed':
        return Colors.green;
      case 'rejected':
        return Colors.red;
      default:
        return Colors.grey;
    }
  }

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

      if (response.statusCode == 200) {
        HapticFeedback.mediumImpact();
        
        final data = response.data;
        final actionName = data['action']?.toString() ?? '推进';
        final medicineName = data['medicine_name']?.toString() ?? '药品';

        if (mounted) {
          showModalBottomSheet(
            context: context,
            backgroundColor: const Color(0xFF00796B),
            shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
            builder: (context) {
              return Padding(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.check_circle_outline, color: Colors.white, size: 64),
                    const SizedBox(height: 16),
                    Text(
                      '[$medicineName] $actionName成功！',
                      style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      '处方追踪码流转状态已自动更新！',
                      style: TextStyle(color: Colors.white70, fontSize: 14),
                    ),
                    const SizedBox(height: 24),
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton(
                        onPressed: () => Navigator.pop(context),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.white,
                          foregroundColor: const Color(0xFF00796B),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                        child: const Text('我知道了', style: TextStyle(fontWeight: FontWeight.bold)),
                      ),
                    ),
                  ],
                ),
              );
            },
          );
        }
        
        _fetchPrescriptions(refresh: true);
      }
    } on DioException catch (e) {
      final errorMsg = e.response?.data['error']?.toString() ?? e.message ?? '未知网络错误';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('扫码配药失败: $errorMsg'),
          backgroundColor: Colors.red,
        ),
      );
    } finally {
      setState(() {
        _isLoading = false;
      });
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

  Widget _buildPrescriptionList(String status) {
    return RefreshIndicator(
      onRefresh: () => _fetchPrescriptions(refresh: true),
      color: const Color(0xFF00796B),
      child: _prescriptions.isEmpty && !_isLoading
          ? ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: const [
                Padding(
                  padding: EdgeInsets.symmetric(vertical: 120.0),
                  child: Center(child: Text('当前分类无处方记录', style: TextStyle(color: Colors.grey, fontSize: 14))),
                ),
              ],
            )
          : ListView.builder(
              padding: const EdgeInsets.fromLTRB(20.0, 20.0, 20.0, 110.0),
              itemCount: _prescriptions.length + (_isLoading ? 1 : 0),
              itemBuilder: (context, index) {
                if (index == _prescriptions.length) {
                  return const Padding(
                    padding: EdgeInsets.symmetric(vertical: 20.0),
                    child: Center(child: CircularProgressIndicator(color: Color(0xFF00796B))),
                  );
                }
                final prescription = _prescriptions[index];
                return Padding(
                  padding: const EdgeInsets.only(bottom: 16.0),
                  child: AnimatedScaleButton(
                    onTap: () async {
                      final changed = await Navigator.push<bool>(
                        context,
                        MaterialPageRoute(
                          builder: (context) => PrescriptionDetailPage(prescriptionId: prescription.id),
                        ),
                      );
                      if (changed == true) {
                        _fetchPrescriptions(refresh: true);
                      }
                    },
                    child: GlassCard(
                      margin: EdgeInsets.zero,
                      padding: const EdgeInsets.all(20.0),
                      borderRadius: 24,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Row(
                                children: [
                                  const Icon(CupertinoIcons.doc_text, color: Colors.grey, size: 18),
                                  const SizedBox(width: 8),
                                  Text(
                                    prescription.prescriptionCode,
                                    style: TextStyle(
                                      fontWeight: FontWeight.w900,
                                      fontSize: 15,
                                      color: Theme.of(context).brightness == Brightness.dark ? Colors.white : const Color(0xFF1E293B),
                                    ),
                                  ),
                                ],
                              ),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: _getStatusColor(prescription.status).withValues(alpha: 0.12),
                                  borderRadius: BorderRadius.circular(8),
                                  border: Border.all(color: _getStatusColor(prescription.status).withValues(alpha: 0.25), width: 0.8),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Container(
                                      width: 5,
                                      height: 5,
                                      decoration: BoxDecoration(
                                        shape: BoxShape.circle,
                                        color: _getStatusColor(prescription.status),
                                      ),
                                    ),
                                    const SizedBox(width: 5),
                                    Text(
                                      prescription.statusText,
                                      style: TextStyle(
                                        color: _getStatusColor(prescription.status),
                                        fontSize: 10,
                                        fontWeight: FontWeight.w900,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 14),
                          const Divider(height: 1, color: Colors.black12),
                          const SizedBox(height: 14),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      '患者：${prescription.patientName ?? "未知"}',
                                      style: TextStyle(
                                        fontSize: 13,
                                        fontWeight: FontWeight.w800,
                                        color: Theme.of(context).brightness == Brightness.dark ? Colors.white70 : const Color(0xFF334155),
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      '科室/医生：${prescription.doctorName ?? "未知"}',
                                      style: const TextStyle(fontSize: 12, color: Colors.grey),
                                    ),
                                  ],
                                ),
                              ),
                              Column(
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  Text(
                                    prescription.createdAt.split('T')[0],
                                    style: const TextStyle(fontSize: 12, color: Colors.grey),
                                  ),
                                  const SizedBox(height: 4),
                                  const Row(
                                    children: [
                                      Text('详情', style: TextStyle(fontSize: 12, color: Color(0xFF00796B), fontWeight: FontWeight.bold)),
                                      SizedBox(width: 2),
                                      Icon(CupertinoIcons.chevron_right, size: 14, color: Color(0xFF00796B)),
                                    ],
                                  )
                                ],
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                );
              },
            ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        title: const Text('处方审核与配药'),
        backgroundColor: Colors.transparent,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(CupertinoIcons.barcode_viewfinder, color: Color(0xFF00796B), size: 24),
            onPressed: _handleScanCode,
            tooltip: '扫码配药复核',
          ),
          const SizedBox(width: 12),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(48),
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 20),
            decoration: BoxDecoration(
              color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.04),
              borderRadius: BorderRadius.circular(16),
            ),
            child: TabBar(
              controller: _tabController,
              isScrollable: true,
              tabAlignment: TabAlignment.start,
              dividerColor: Colors.transparent,
              indicator: BoxDecoration(
                color: const Color(0xFF00796B),
                borderRadius: BorderRadius.circular(12),
              ),
              labelColor: Colors.white,
              unselectedLabelColor: isDark ? Colors.white60 : Colors.black54,
              labelStyle: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13),
              unselectedLabelStyle: const TextStyle(fontWeight: FontWeight.normal, fontSize: 13),
              tabs: _tabs.map((t) => Tab(text: t['title'])).toList(),
            ),
          ),
        ),
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
            child: TabBarView(
              controller: _tabController,
              children: _tabs.map((t) => _buildPrescriptionList(t['status'] as String)).toList(),
            ),
          ),
        ],
      ),
    );
  }
}
