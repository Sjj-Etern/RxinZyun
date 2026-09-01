import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/providers/auth_provider.dart';
import 'package:provider/provider.dart';

class RobotManagementPage extends StatefulWidget {
  const RobotManagementPage({super.key});

  @override
  State<RobotManagementPage> createState() => _RobotManagementPageState();
}

class _RobotManagementPageState extends State<RobotManagementPage> {
  List<dynamic> _robots = [];
  bool _loading = true;

  static const _status = {
    'available': ('空闲可调度', Color(0xFF15803D)),
    'busy': ('配送任务中', Color(0xFF0369A1)),
    'disabled': ('已停用', Color(0xFF6B7280)),
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final response = await ApiClient().dio.get('/api/robots');
      if (mounted) setState(() => _robots = response.data as List);
    } on DioException catch (error) {
      _show(error.response?.data?['error']?.toString() ?? '机器人列表加载失败');
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

  Future<void> _edit([Map<String, dynamic>? robot]) async {
    final code = TextEditingController(text: robot?['code']?.toString() ?? '');
    final name = TextEditingController(text: robot?['name']?.toString() ?? '');
    var status = robot?['status']?.toString() ?? 'available';
    final result = await showDialog<Map<String, String>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text(robot == null ? '新增机器人' : '编辑机器人'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: code,
                textCapitalization: TextCapitalization.characters,
                decoration: const InputDecoration(
                  labelText: '设备编号',
                  hintText: '例如 R003',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: name,
                decoration: const InputDecoration(labelText: '机器人名称'),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: status,
                decoration: const InputDecoration(labelText: '当前状态'),
                items: _status.entries
                    .map(
                      (item) => DropdownMenuItem(
                        value: item.key,
                        child: Text(item.value.$1),
                      ),
                    )
                    .toList(),
                onChanged: (value) =>
                    setDialogState(() => status = value ?? status),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, {
                'code': code.text.trim().toUpperCase(),
                'name': name.text.trim(),
                'status': status,
              }),
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );
    code.dispose();
    name.dispose();
    if (result == null) return;
    try {
      final response = robot == null
          ? await ApiClient().dio.post('/api/robots', data: result)
          : await ApiClient().dio.put(
              '/api/robots/${robot['id']}',
              data: result,
            );
      _show(response.data['message']?.toString() ?? '保存成功');
      await _load();
    } on DioException catch (error) {
      _show(error.response?.data?['error']?.toString() ?? '保存失败');
    }
  }

  Future<void> _restore(Map<String, dynamic> robot) async {
    try {
      final response = await ApiClient().dio.put(
        '/api/robots/${robot['id']}',
        data: {
          'code': robot['code'],
          'name': robot['name'],
          'status': 'available',
        },
      );
      _show('测试阶段：${response.data['message'] ?? '已恢复为空闲状态'}');
      await _load();
    } on DioException catch (error) {
      _show(error.response?.data?['error']?.toString() ?? '恢复空闲状态失败');
    }
  }

  Future<void> _delete(Map<String, dynamic> robot) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除机器人'),
        content: Text('确认删除 ${robot['code']} · ${robot['name']}？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('删除'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      final response = await ApiClient().dio.delete(
        '/api/robots/${robot['id']}',
      );
      _show(response.data['message']?.toString() ?? '机器人已删除');
      await _load();
    } on DioException catch (error) {
      _show(error.response?.data?['error']?.toString() ?? '删除失败');
    }
  }

  @override
  Widget build(BuildContext context) {
    final isAdmin = context.watch<AuthProvider>().currentUser?.isAdmin == true;
    return Scaffold(
      appBar: AppBar(
        title: const Text('机器人管理'),
        actions: [
          IconButton(onPressed: _load, icon: const Icon(Icons.refresh)),
        ],
      ),
      floatingActionButton: isAdmin
          ? FloatingActionButton.extended(
              onPressed: () => _edit(),
              icon: const Icon(Icons.add),
              label: const Text('新增机器人'),
            )
          : null,
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
                children: [
                  if (isAdmin)
                    Container(
                      padding: const EdgeInsets.all(12),
                      margin: const EdgeInsets.only(bottom: 12),
                      decoration: BoxDecoration(
                        color: const Color(0xFFF59E0B).withValues(alpha: .12),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: const Text(
                        '测试阶段工具：可将配送任务中的机器人手动恢复为空闲状态。',
                        style: TextStyle(
                          color: Color(0xFFB45309),
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  if (_robots.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(32),
                      child: Center(child: Text('暂无机器人')),
                    ),
                  ..._robots.map((item) {
                    final robot = Map<String, dynamic>.from(item as Map);
                    final meta =
                        _status[robot['status']] ?? _status['disabled']!;
                    return Card(
                      margin: const EdgeInsets.only(bottom: 12),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          children: [
                            Row(
                              children: [
                                CircleAvatar(
                                  backgroundColor: meta.$2.withValues(
                                    alpha: .12,
                                  ),
                                  child: Icon(
                                    Icons.smart_toy_outlined,
                                    color: meta.$2,
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        robot['code']?.toString() ?? '-',
                                        style: const TextStyle(
                                          fontSize: 17,
                                          fontWeight: FontWeight.w800,
                                        ),
                                      ),
                                      Text(
                                        robot['name']?.toString() ?? '-',
                                        style: const TextStyle(
                                          color: Colors.grey,
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                Chip(
                                  label: Text(meta.$1),
                                  labelStyle: TextStyle(
                                    color: meta.$2,
                                    fontWeight: FontWeight.w700,
                                  ),
                                  backgroundColor: meta.$2.withValues(
                                    alpha: .1,
                                  ),
                                ),
                              ],
                            ),
                            if (isAdmin) ...[
                              const Divider(height: 24),
                              Wrap(
                                spacing: 8,
                                runSpacing: 8,
                                alignment: WrapAlignment.end,
                                children: [
                                  OutlinedButton.icon(
                                    onPressed: () => _edit(robot),
                                    icon: const Icon(
                                      Icons.edit_outlined,
                                      size: 18,
                                    ),
                                    label: const Text('编辑'),
                                  ),
                                  if (robot['status'] != 'available')
                                    OutlinedButton.icon(
                                      onPressed: () => _restore(robot),
                                      icon: const Icon(
                                        Icons.science_outlined,
                                        size: 18,
                                      ),
                                      label: const Text('测试：恢复为空闲'),
                                    ),
                                  TextButton.icon(
                                    onPressed: () => _delete(robot),
                                    icon: const Icon(
                                      Icons.delete_outline,
                                      size: 18,
                                    ),
                                    label: const Text('删除'),
                                  ),
                                ],
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
