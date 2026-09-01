import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/core/theme/glass_card.dart';

class ScanPage extends StatefulWidget {
  const ScanPage({super.key});

  @override
  State<ScanPage> createState() => _ScanPageState();
}

class _TraceEntry {
  final String traceCode;
  final String medicineName;
  final String status;
  final String action;
  final String time;
  final bool isError;
  final String? message;

  const _TraceEntry({
    required this.traceCode,
    required this.medicineName,
    required this.status,
    required this.action,
    required this.time,
    this.isError = false,
    this.message,
  });
}

class _ScanPageState extends State<ScanPage> {
  final TextEditingController _scanController = TextEditingController();
  final FocusNode _scanFocusNode = FocusNode();
  final TextEditingController _searchController = TextEditingController();
  final List<_TraceEntry> _history = [];

  _TraceEntry? _searchResult;
  String _searchError = '';
  bool _processing = false;
  String _lastCode = '';

  @override
  void dispose() {
    _scanController.dispose();
    _scanFocusNode.dispose();
    _searchController.dispose();
    super.dispose();
  }

  List<String> _traceCodeCandidates(String value) {
    final raw = value.trim();
    if (raw.isEmpty) return [];

    final candidates = <String>{raw};
    try {
      final decoded = Uri.decodeComponent(raw).trim();
      if (decoded.isNotEmpty) candidates.add(decoded);
    } catch (_) {
      // 将原始值交给后端，返回明确的业务错误。
    }

    for (final text in List<String>.from(candidates)) {
      final uri = Uri.tryParse(text);
      if (uri != null) {
        for (final key in ['trace_code', 'traceCode', 'code', 'c']) {
          final param = uri.queryParameters[key];
          if (param != null && param.trim().isNotEmpty) {
            candidates.add(param.trim());
          }
        }
      }
    }

    for (final text in List<String>.from(candidates)) {
      final compact = text.replaceAll(RegExp(r'[\s-]'), '');
      if (RegExp(r'^\d{20,}$').hasMatch(compact)) candidates.add(compact);
      for (final match in RegExp(r'\d{20,}').allMatches(text)) {
        candidates.add(match.group(0)!);
      }
    }
    return candidates.where((item) => item.isNotEmpty).toList();
  }

  String _normalizeTraceCode(String value) {
    final candidates = _traceCodeCandidates(value);
    return candidates.firstWhere(
      (candidate) => RegExp(r'^\d{20,}$').hasMatch(candidate),
      orElse: () => candidates.isEmpty ? value.trim() : candidates.first,
    );
  }

  String _now() {
    final now = DateTime.now();
    return '${now.year}-${now.month.toString().padLeft(2, '0')}-'
        '${now.day.toString().padLeft(2, '0')} '
        '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}:'
        '${now.second.toString().padLeft(2, '0')}';
  }

  _TraceEntry _entryFromData(
    Map<String, dynamic> data,
    String fallbackCode, {
    String action = '',
  }) {
    return _TraceEntry(
      traceCode: data['trace_code']?.toString() ?? fallbackCode,
      medicineName: data['medicine_name']?.toString() ?? '未命名药品',
      status: data['status']?.toString() ?? 'pending',
      action: data['action']?.toString() ?? action,
      time: _now(),
    );
  }

  String _errorMessage(DioException error, String fallback) {
    final data = error.response?.data;
    if (data is Map && data['error'] != null) {
      return data['error'].toString();
    }
    return error.message ?? fallback;
  }

  Future<void> _processCode(String value) async {
    final code = _normalizeTraceCode(value);
    if (code.isEmpty || _processing || code == _lastCode) return;

    setState(() {
      _processing = true;
      _lastCode = code;
      _searchError = '';
    });

    try {
      final response = await ApiClient().dio.post(
        '/api/medicine-trace-codes/scan-by-code',
        data: {'trace_code': code},
      );
      final data = Map<String, dynamic>.from(response.data as Map);
      final entry = _entryFromData(
        data,
        code,
        action: data['action']?.toString() ?? '扫码',
      );
      setState(() {
        _history.removeWhere(
          (item) => item.traceCode == entry.traceCode && !item.isError,
        );
        _history.insert(0, entry);
        _searchResult = entry;
      });
      SystemSound.play(SystemSoundType.click);
      HapticFeedback.lightImpact();
      final message = data['completed'] == true
          ? '追溯码已完成全部流程'
          : '${entry.action.isEmpty ? '扫码' : entry.action}成功';
      _showMessage(message, false);
    } on DioException catch (error) {
      final message = _errorMessage(error, '扫码失败，请重试');
      setState(() {
        _history.insert(
          0,
          _TraceEntry(
            traceCode: code,
            medicineName: '扫码失败',
            status: 'error',
            action: '扫码失败',
            time: _now(),
            isError: true,
            message: message,
          ),
        );
      });
      HapticFeedback.heavyImpact();
      _showMessage(message, true);
    } finally {
      if (mounted) {
        setState(() => _processing = false);
        Timer(const Duration(milliseconds: 1200), () {
          if (mounted && !_processing && _lastCode == code) {
            setState(() => _lastCode = '');
          }
        });
      }
    }
  }

  Future<void> _handleLookup() async {
    final code = _normalizeTraceCode(_searchController.text);
    if (code.isEmpty) return;

    setState(() => _searchError = '');
    try {
      final response = await ApiClient().dio.get(
        '/api/medicine-trace-codes/lookup',
        queryParameters: {'trace_code': code},
      );
      final data = Map<String, dynamic>.from(response.data as Map);
      setState(() => _searchResult = _entryFromData(data, code));
    } on DioException catch (error) {
      final message = _errorMessage(error, '追溯码未找到');
      setState(() {
        _searchResult = null;
        _searchError = message;
      });
      _showMessage(message, true);
    }
  }

  Future<void> _submitScanInput(String value) async {
    _scanController.clear();
    await _processCode(value);
    if (mounted) _scanFocusNode.requestFocus();
  }

  void _showMessage(String message, bool isError) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: isError ? Colors.redAccent : const Color(0xFF00897B),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(milliseconds: 2200),
        ),
      );
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'pending':
        return '待出库';
      case 'scanned_outbound':
        return '已出库';
      case 'scanned_confirm':
        return '已完成';
      case 'scanned_identify':
        return '待出库（旧状态）';
      case 'error':
        return '扫码失败';
      default:
        return status;
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'scanned_confirm':
        return const Color(0xFF16A34A);
      case 'scanned_outbound':
        return const Color(0xFF7C3AED);
      case 'error':
        return const Color(0xFFDC2626);
      default:
        return const Color(0xFF2563EB);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Scaffold(
      appBar: AppBar(title: const Text('出库追溯')),
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: isDark
                ? [const Color(0xFF090C15), const Color(0xFF0B1B2A)]
                : [const Color(0xFFEAF6FF), const Color(0xFFEDFDF8)],
          ),
        ),
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 28),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.fromLTRB(8, 4, 8, 14),
                  child: Text(
                    '使用扫码枪完成药品出库与接收确认，实时保留本次操作记录。',
                    style: TextStyle(color: Colors.grey, fontSize: 13),
                  ),
                ),
                GlassCard(
                  margin: EdgeInsets.zero,
                  borderRadius: 24,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: const Color(
                                0xFF009688,
                              ).withValues(alpha: .12),
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(
                              CupertinoIcons.barcode_viewfinder,
                              color: Color(0xFF00897B),
                              size: 28,
                            ),
                          ),
                          const SizedBox(width: 12),
                          const Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  '等待扫码输入',
                                  style: TextStyle(
                                    fontSize: 18,
                                    fontWeight: FontWeight.w900,
                                  ),
                                ),
                                SizedBox(height: 4),
                                Text(
                                  '请将光标放在输入框，扫码枪读取后按回车自动提交。',
                                  style: TextStyle(
                                    color: Colors.grey,
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 18),
                      TextField(
                        controller: _scanController,
                        focusNode: _scanFocusNode,
                        autofocus: true,
                        textInputAction: TextInputAction.done,
                        onSubmitted: (value) =>
                            unawaited(_submitScanInput(value)),
                        decoration: const InputDecoration(
                          prefixIcon: Icon(CupertinoIcons.barcode),
                          hintText: '输入或扫描药品追溯码',
                          labelText: '扫码输入',
                        ),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            _processing ? '正在写入出库记录…' : '每次扫码推进一个业务节点',
                            style: const TextStyle(
                              color: Colors.grey,
                              fontSize: 11,
                            ),
                          ),
                          const Text(
                            '2 次完成闭环',
                            style: TextStyle(color: Colors.grey, fontSize: 11),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                GlassCard(
                  margin: EdgeInsets.zero,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '手动查询追溯码',
                        style: TextStyle(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 10),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _searchController,
                              textInputAction: TextInputAction.search,
                              onSubmitted: (_) => _handleLookup(),
                              decoration: const InputDecoration(
                                prefixIcon: Icon(CupertinoIcons.number_square),
                                hintText: '仅查询当前状态，不推进流程',
                                isDense: true,
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          FilledButton(
                            onPressed: _handleLookup,
                            child: const Text('查询'),
                          ),
                        ],
                      ),
                      if (_searchResult != null) ...[
                        const SizedBox(height: 12),
                        _buildResultCard(_searchResult!, isDark),
                      ],
                      if (_searchError.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        Text(
                          _searchError,
                          style: const TextStyle(
                            color: Colors.redAccent,
                            fontSize: 12,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                GlassCard(
                  margin: EdgeInsets.zero,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            '扫码记录',
                            style: TextStyle(
                              fontSize: 17,
                              fontWeight: FontWeight.w900,
                            ),
                          ),
                          Text(
                            '${_history.length.toString().padLeft(2, '0')} 条',
                            style: const TextStyle(
                              color: Colors.grey,
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      if (_history.isEmpty)
                        const SizedBox(
                          height: 120,
                          child: Center(
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  CupertinoIcons.barcode_viewfinder,
                                  color: Colors.grey,
                                  size: 34,
                                ),
                                SizedBox(height: 8),
                                Text(
                                  '等待第一条扫码记录',
                                  style: TextStyle(
                                    fontWeight: FontWeight.w700,
                                    color: Colors.grey,
                                  ),
                                ),
                                SizedBox(height: 3),
                                Text(
                                  '扫描成功或失败后，记录会从这里显示',
                                  style: TextStyle(
                                    color: Colors.grey,
                                    fontSize: 11,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        )
                      else
                        SizedBox(
                          height: 360,
                          child: ListView.separated(
                            itemCount: _history.length,
                            separatorBuilder: (_, _) =>
                                const Divider(height: 1),
                            itemBuilder: (context, index) => _buildHistoryEntry(
                              _history[index],
                              index,
                              isDark,
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
      ),
    );
  }

  Widget _buildResultCard(_TraceEntry entry, bool isDark) {
    final color = _statusColor(entry.status);
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .1),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: .22)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  '查询结果',
                  style: TextStyle(color: Colors.grey, fontSize: 11),
                ),
                const SizedBox(height: 3),
                Text(
                  entry.medicineName,
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    color: isDark ? Colors.white : const Color(0xFF1E293B),
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  entry.traceCode,
                  style: const TextStyle(color: Colors.grey, fontSize: 11),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          _StatusPill(label: _statusLabel(entry.status), color: color),
        ],
      ),
    );
  }

  Widget _buildHistoryEntry(_TraceEntry entry, int index, bool isDark) {
    final color = _statusColor(entry.status);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 28,
            child: Text(
              (index + 1).toString().padLeft(2, '0'),
              style: const TextStyle(color: Colors.grey, fontSize: 12),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  entry.isError ? entry.message ?? '扫码失败' : entry.medicineName,
                  style: TextStyle(
                    fontWeight: FontWeight.w800,
                    color: entry.isError
                        ? Colors.redAccent
                        : (isDark ? Colors.white : const Color(0xFF1E293B)),
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  entry.traceCode,
                  style: const TextStyle(color: Colors.grey, fontSize: 11),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 3),
                Text(
                  entry.time,
                  style: const TextStyle(color: Colors.grey, fontSize: 11),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          _StatusPill(label: _statusLabel(entry.status), color: color),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  final String label;
  final Color color;

  const _StatusPill({required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}
