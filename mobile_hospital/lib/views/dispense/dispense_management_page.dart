import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:his_mobile/core/network/api_client.dart';

class DispenseManagementPage extends StatefulWidget {
  const DispenseManagementPage({super.key});

  @override
  State<DispenseManagementPage> createState() => _DispenseManagementPageState();
}

class _DispenseManagementPageState extends State<DispenseManagementPage> {
  List<dynamic> _prescriptions = [];
  List<dynamic> _robots = [];
  bool _loading = true;
  int? _busyId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final responses = await Future.wait([
        ApiClient().dio.get(
          '/api/prescriptions',
          queryParameters: {'status': 'approved', 'page': 1, 'pageSize': 200},
        ),
        ApiClient().dio.get('/api/robots'),
      ]);
      if (!mounted) return;
      setState(() {
        _prescriptions = responses[0].data['list'] as List? ?? [];
        _robots = responses[1].data as List? ?? [];
      });
    } on DioException catch (error) {
      _show(error.response?.data?['error']?.toString() ?? '发药管理数据加载失败');
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

  Future<String?> _selectRobotCode() async {
    final available = _robots
        .where((item) => item['status'] == 'available')
        .toList();
    final controller = TextEditingController();
    final code = await showDialog<String>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('选择配送机器人'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextField(
                  controller: controller,
                  textCapitalization: TextCapitalization.characters,
                  onChanged: (_) => setDialogState(() {}),
                  decoration: const InputDecoration(
                    labelText: '机器人设备编号',
                    hintText: '例如 R001',
                    prefixIcon: Icon(Icons.smart_toy_outlined),
                  ),
                ),
                const SizedBox(height: 14),
                const Text(
                  '空闲机器人',
                  style: TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 8),
                if (available.isEmpty)
                  const Text('暂无空闲机器人', style: TextStyle(color: Colors.grey)),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: available
                      .map(
                        (robot) => ChoiceChip(
                          label: Text('${robot['code']} · ${robot['name']}'),
                          selected:
                              controller.text.trim().toUpperCase() ==
                              robot['code'],
                          onSelected: (_) => setDialogState(
                            () => controller.text =
                                robot['code']?.toString() ?? '',
                          ),
                        ),
                      )
                      .toList(),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: controller.text.trim().isEmpty
                  ? null
                  : () => Navigator.pop(
                      dialogContext,
                      controller.text.trim().toUpperCase(),
                    ),
              child: const Text('确认选择'),
            ),
          ],
        ),
      ),
    );
    controller.dispose();
    return code;
  }

  Future<void> _dispense(Map<String, dynamic> prescription) async {
    final robotCode = await _selectRobotCode();
    if (robotCode == null || robotCode.isEmpty) return;
    setState(() => _busyId = prescription['id'] as int);
    try {
      final response = await ApiClient().dio.put(
        '/api/prescriptions/${prescription['id']}/dispense',
        data: {'robot_code': robotCode},
      );
      _show(response.data['message']?.toString() ?? '已开始配送');
      await _load();
    } on DioException catch (error) {
      _show(error.response?.data?['error']?.toString() ?? '发药确认失败');
    } finally {
      if (mounted) setState(() => _busyId = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final availableCount = _robots
        .where((item) => item['status'] == 'available')
        .length;
    return Scaffold(
      appBar: AppBar(
        title: const Text('发药管理'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: _SummaryCard(
                          value: '${_prescriptions.length}',
                          label: '待确认发药处方',
                          color: const Color(0xFF168A8D),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _SummaryCard(
                          value: '$availableCount',
                          label: '空闲机器人',
                          color: const Color(0xFF15803D),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  if (_prescriptions.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(40),
                      child: Center(child: Text('暂无待确认发药处方')),
                    ),
                  ..._prescriptions.map((item) {
                    final prescription = Map<String, dynamic>.from(item as Map);
                    final id = prescription['id'] as int;
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
                                    prescription['prescription_code']
                                            ?.toString() ??
                                        '#$id',
                                    style: const TextStyle(
                                      fontWeight: FontWeight.w900,
                                      fontSize: 16,
                                    ),
                                  ),
                                ),
                                const Chip(label: Text('待确认发药')),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Text('病人：${prescription['patient_name'] ?? '-'}'),
                            const SizedBox(height: 4),
                            Text(
                              '诊断：${prescription['diagnosis'] ?? '-'}',
                              style: const TextStyle(color: Colors.grey),
                            ),
                            const SizedBox(height: 14),
                            SizedBox(
                              width: double.infinity,
                              child: FilledButton.icon(
                                onPressed: _busyId == id
                                    ? null
                                    : () => _dispense(prescription),
                                icon: const Icon(Icons.local_shipping_outlined),
                                label: Text(
                                  _busyId == id ? '正在确认…' : '选择机器人并确认发药',
                                ),
                              ),
                            ),
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

class _SummaryCard extends StatelessWidget {
  final String value;
  final String label;
  final Color color;

  const _SummaryCard({
    required this.value,
    required this.label,
    required this.color,
  });

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .1),
      borderRadius: BorderRadius.circular(18),
      border: Border.all(color: color.withValues(alpha: .22)),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 28,
            fontWeight: FontWeight.w900,
          ),
        ),
        Text(label, style: const TextStyle(color: Colors.grey, fontSize: 12)),
      ],
    ),
  );
}
