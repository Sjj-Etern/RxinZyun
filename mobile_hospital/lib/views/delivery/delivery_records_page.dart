import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/providers/auth_provider.dart';
import 'package:his_mobile/views/delivery/realtime_face_verify_page.dart';
import 'package:provider/provider.dart';

class DeliveryRecordsPage extends StatefulWidget {
  const DeliveryRecordsPage({super.key});

  @override
  State<DeliveryRecordsPage> createState() => _DeliveryRecordsPageState();
}

class _DeliveryRecordsPageState extends State<DeliveryRecordsPage> {
  List<dynamic> _records = [];
  bool _loading = true;
  Timer? _timer;

  static const _statusMeta = {
    'delivering': ('配送中', Color(0xFF0369A1), Color(0xFFE0F2FE)),
    'arrived': ('待医生核验', Color(0xFFB45309), Color(0xFFFEF3C7)),
    'unlocked': ('已核验开锁', Color(0xFF15803D), Color(0xFFDCFCE7)),
  };

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final response = await ApiClient().dio.get('/api/delivery-records');
      if (mounted) setState(() => _records = response.data as List);
    } on DioException catch (error) {
      _show(error.response?.data?['error']?.toString() ?? '配送记录加载失败');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _show(String message) {
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  Future<void> _arrival(int id) async {
    try {
      final response = await ApiClient().dio.post(
        '/api/delivery-records/$id/simulate-arrival',
      );
      _show(response.data['message']?.toString() ?? '机器人已到达');
      await _load();
    } on DioException catch (error) {
      _show(error.response?.data?['error']?.toString() ?? '模拟到达失败');
    }
  }

  Future<void> _openVerify(Map<String, dynamic> record) async {
    final verified = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => RealtimeFaceVerifyPage(
          recordId: record['id'] as int,
          medicineName: record['medicine_name']?.toString() ?? '配送药品',
          robotCode: record['robot_code']?.toString() ?? '-',
        ),
      ),
    );
    if (verified == true) await _load();
  }

  @override
  Widget build(BuildContext context) {
    final user = context.watch<AuthProvider>().currentUser;
    return Scaffold(
      appBar: AppBar(
        title: const Text('配送记录'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(16),
                children: [
                  if (_records.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(48),
                      child: Center(child: Text('暂无配送记录')),
                    ),
                  ..._records.map((item) {
                    final record = Map<String, dynamic>.from(item as Map);
                    final meta =
                        _statusMeta[record['status']] ??
                        _statusMeta['delivering']!;
                    final canArrival =
                        user?.isPharmacist == true &&
                        record['status'] == 'delivering';
                    final canVerify =
                        user?.isDoctor == true && record['status'] == 'arrived';
                    final prescription =
                        record['prescription_code']?.toString() ??
                        '#${record['prescription_id']}';
                    return Card(
                      margin: const EdgeInsets.only(bottom: 12),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    '${record['medicine_name']} × ${record['quantity']}${record['unit']}',
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w900,
                                      fontSize: 16,
                                    ),
                                  ),
                                ),
                                Chip(
                                  label: Text(meta.$1),
                                  labelStyle: TextStyle(
                                    color: meta.$2,
                                    fontWeight: FontWeight.w800,
                                  ),
                                  backgroundColor: meta.$3,
                                  side: BorderSide(
                                    color: meta.$2.withValues(alpha: .3),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 10),
                            Text(
                              '处方：$prescription · 病人：${record['patient_name'] ?? '-'}',
                            ),
                            const SizedBox(height: 5),
                            Text(
                              '配送机器人：${record['robot_code']} · ${record['robot_name']}',
                              style: const TextStyle(color: Colors.grey),
                            ),
                            const SizedBox(height: 5),
                            Text(
                              '发药/核验：${record['dispatched_by_name'] ?? '-'}${record['verified_by_name'] == null ? '' : ' / ${record['verified_by_name']}'}',
                              style: const TextStyle(color: Colors.grey),
                            ),
                            if (canArrival || canVerify) ...[
                              const SizedBox(height: 14),
                              SizedBox(
                                width: double.infinity,
                                child: canArrival
                                    ? FilledButton.icon(
                                        onPressed: () =>
                                            _arrival(record['id'] as int),
                                        icon: const Icon(
                                          Icons.local_shipping_outlined,
                                        ),
                                        label: const Text('模拟机器人到达'),
                                      )
                                    : FilledButton.icon(
                                        onPressed: () => _openVerify(record),
                                        icon: const Icon(
                                          Icons.face_retouching_natural,
                                        ),
                                        label: const Text('打开摄像头实时核验'),
                                      ),
                              ),
                            ],
                          ],
                        ),
                      ),
                    );
                  }),
                ],
              ),
            ),
    );
  }
}
