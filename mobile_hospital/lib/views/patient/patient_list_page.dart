import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'dart:ui';
import 'package:dio/dio.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/data/models/patient_model.dart';
import 'patient_form_page.dart';
import 'package:his_mobile/core/theme/glass_card.dart';
import 'package:his_mobile/core/widgets/animated_scale_button.dart';

class PatientListPage extends StatefulWidget {
  const PatientListPage({super.key});

  @override
  State<PatientListPage> createState() => _PatientListPageState();
}

class _PatientListPageState extends State<PatientListPage> {
  final List<PatientModel> _patients = [];
  bool _isLoading = false;
  String _keyword = '';
  final _searchController = TextEditingController();

  int _page = 1;
  int _total = 0;
  final int _pageSize = 15;

  @override
  void initState() {
    super.initState();
    _fetchPatients(refresh: true);
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _fetchPatients({bool refresh = false}) async {
    if (_isLoading) return;
    if (!refresh && _patients.length >= _total) return; // 已加载全部

    setState(() {
      _isLoading = true;
    });

    if (refresh) {
      _page = 1;
      _patients.clear();
    }

    try {
      final response = await ApiClient().dio.get(
        '/api/patients',
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
          _patients.addAll(list.map((p) => PatientModel.fromJson(p as Map<String, dynamic>)));
          _page++;
        });
      }
    } on DioException catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('加载患者列表失败: ${e.message}')),
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
    _fetchPatients(refresh: true);
  }

  Future<void> _navigateToAddPatient() async {
    final added = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (context) => const PatientFormPage()),
    );
    if (added == true) {
      _fetchPatients(refresh: true);
    }
  }

  Future<void> _navigateToEditPatient(PatientModel patient) async {
    final updated = await Navigator.push<bool>(
      context,
      MaterialPageRoute(builder: (context) => PatientFormPage(patient: patient)),
    );
    if (updated == true) {
      _fetchPatients(refresh: true);
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

    return Scaffold(
      appBar: AppBar(
        title: const Text('患者管理'),
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
                          hintText: '搜索患者姓名或手机号',
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

            // 患者列表
            Expanded(
              child: RefreshIndicator(
                onRefresh: () => _fetchPatients(refresh: true),
                color: const Color(0xFF00796B),
                child: _patients.isEmpty && !_isLoading
                    ? ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        children: const [
                          Padding(
                            padding: EdgeInsets.symmetric(vertical: 120.0),
                            child: Center(child: Text('无匹配患者记录', style: TextStyle(color: Colors.grey, fontSize: 14))),
                          ),
                        ],
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.fromLTRB(20.0, 12.0, 20.0, 110.0), // 底部留空，防止被底栏遮挡
                        itemCount: _patients.length + (_isLoading ? 1 : 0),
                        itemBuilder: (context, index) {
                          if (index == _patients.length) {
                            return const Padding(
                              padding: EdgeInsets.symmetric(vertical: 20.0),
                              child: Center(child: CircularProgressIndicator(color: Color(0xFF00796B))),
                            );
                          }

                          final patient = _patients[index];

                          return Padding(
                            padding: const EdgeInsets.only(bottom: 16.0),
                            child: GlassCard(
                              margin: EdgeInsets.zero,
                              padding: const EdgeInsets.all(20.0),
                              borderRadius: 24,
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  // 头部：姓名、性别、年龄、编辑按钮
                                  Row(
                                    children: [
                                      CircleAvatar(
                                        radius: 20,
                                        backgroundColor: patient.gender == '男' 
                                            ? const Color(0xFF007AFF).withValues(alpha: 0.1) 
                                            : const Color(0xFFFF2D55).withValues(alpha: 0.1),
                                        child: Icon(
                                          CupertinoIcons.person_fill,
                                          color: patient.gender == '男' ? const Color(0xFF007AFF) : const Color(0xFFFF2D55),
                                          size: 18,
                                        ),
                                      ),
                                      const SizedBox(width: 14),
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Row(
                                              children: [
                                                Text(
                                                  patient.name,
                                                  style: TextStyle(
                                                    fontWeight: FontWeight.w900, 
                                                    fontSize: 16,
                                                    color: isDark ? Colors.white : const Color(0xFF1E293B),
                                                  ),
                                                ),
                                                const SizedBox(width: 8),
                                                Text(
                                                  '${patient.age}岁',
                                                  style: const TextStyle(color: Colors.grey, fontSize: 13),
                                                ),
                                              ],
                                            ),
                                            const SizedBox(height: 2),
                                            Text(
                                              '病历号：${patient.medicalRecordNo}',
                                              style: const TextStyle(color: Colors.grey, fontSize: 12),
                                            ),
                                          ],
                                        ),
                                      ),
                                      AnimatedScaleButton(
                                        onTap: () => _navigateToEditPatient(patient),
                                        child: Container(
                                          padding: const EdgeInsets.all(8),
                                          decoration: BoxDecoration(
                                            color: isDark ? Colors.white.withValues(alpha: 0.04) : Colors.black.withValues(alpha: 0.04),
                                            shape: BoxShape.circle,
                                          ),
                                          child: const Icon(CupertinoIcons.pencil, color: Color(0xFF00796B), size: 16),
                                        ),
                                      ),
                                    ],
                                  ),
                                  if (patient.phone != null && patient.phone!.isNotEmpty) ...[
                                    const SizedBox(height: 12),
                                    const Divider(height: 1, color: Colors.black12),
                                    const SizedBox(height: 12),
                                    Row(
                                      children: [
                                        const Icon(CupertinoIcons.phone, color: Colors.grey, size: 14),
                                        const SizedBox(width: 8),
                                        Text(
                                          patient.phone!,
                                          style: TextStyle(
                                            fontSize: 13,
                                            fontWeight: FontWeight.w800,
                                            color: isDark ? Colors.white70 : const Color(0xFF475569),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ],
                                ],
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
      floatingActionButton: Padding(
        padding: const EdgeInsets.only(bottom: 85.0), // 向上偏移以避开悬浮底栏
        child: FloatingActionButton(
          onPressed: _navigateToAddPatient,
          backgroundColor: const Color(0xFF00796B),
          foregroundColor: Colors.white,
          elevation: 4,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          child: const Icon(CupertinoIcons.plus, size: 22),
        ),
      ),
    );
  }
}
