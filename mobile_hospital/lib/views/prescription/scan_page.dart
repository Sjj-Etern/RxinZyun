import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/core/theme/glass_card.dart';

class ScanPage extends StatefulWidget {
  final int? initialPrescriptionId;

  const ScanPage({super.key, this.initialPrescriptionId});

  @override
  State<ScanPage> createState() => _ScanPageState();
}

class _TraceEntry {
  final String traceCode;
  final String medicineName;
  final String status;
  final String action;
  final String time;
  final bool isImport;
  final String? message;

  const _TraceEntry({
    required this.traceCode,
    required this.medicineName,
    required this.status,
    required this.action,
    required this.time,
    this.isImport = false,
    this.message,
  });
}

class _ScanPageState extends State<ScanPage> {
  final TextEditingController _scanController = TextEditingController();
  final FocusNode _scanFocusNode = FocusNode();
  final TextEditingController _searchController = TextEditingController();
  final List<_TraceEntry> _history = [];
  List<dynamic> _prescriptions = [];
  Map<String, dynamic>? _prescriptionDetail;
  int? _selectedPrescriptionId;
  bool _prescriptionsLoading = true;

  _TraceEntry? _searchResult;
  String _searchError = '';
  bool _processing = false;
  String _confirmingCode = '';
  String _lastCode = '';

  @override
  void initState() {
    super.initState();
    _selectedPrescriptionId = widget.initialPrescriptionId;
    _loadPrescriptions();
  }

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

  Future<void> _loadPrescriptions() async {
    try {
      final response = await ApiClient().dio.get(
        '/api/prescriptions/scan-ready',
      );
      final list = response.data as List? ?? [];
      final preferredId = _selectedPrescriptionId;
      final preferredExists = list.any(
        (item) => (item as Map)['id'] == preferredId,
      );
      final nextId = preferredExists
          ? preferredId
          : (list.isEmpty ? null : (list.first as Map)['id'] as int);
      if (!mounted) return;
      setState(() {
        _prescriptions = list;
        _selectedPrescriptionId = nextId;
        _prescriptionsLoading = false;
      });
      await _loadPrescriptionDetail();
      if (mounted && _selectedPrescriptionId != null) {
        _scanFocusNode.requestFocus();
      }
    } on DioException catch (error) {
      if (!mounted) return;
      setState(() => _prescriptionsLoading = false);
      _showMessage(_errorMessage(error, '可发药处方加载失败'), true);
    }
  }

  Future<void> _loadPrescriptionDetail() async {
    final prescriptionId = _selectedPrescriptionId;
    if (prescriptionId == null) {
      if (mounted) setState(() => _prescriptionDetail = null);
      return;
    }
    try {
      final response = await ApiClient().dio.get(
        '/api/prescriptions/$prescriptionId',
      );
      if (mounted) {
        setState(
          () => _prescriptionDetail = Map<String, dynamic>.from(
            response.data as Map,
          ),
        );
      }
    } on DioException catch (error) {
      _showMessage(_errorMessage(error, '处方明细加载失败'), true);
    }
  }

  Future<void> _selectPrescription(int? prescriptionId) async {
    setState(() {
      _selectedPrescriptionId = prescriptionId;
      _prescriptionDetail = null;
      _history.clear();
      _searchResult = null;
    });
    await _loadPrescriptionDetail();
    if (mounted && _selectedPrescriptionId != null) {
      _scanFocusNode.requestFocus();
    }
  }

  Future<void> _processCode(String value) async {
    final code = _normalizeTraceCode(value);
    if (code.isEmpty || _processing || code == _lastCode) return;
    if (_selectedPrescriptionId == null) {
      _showMessage('请先选择当前处方', true);
      return;
    }

    setState(() {
      _processing = true;
      _lastCode = code;
      _searchError = '';
    });

    try {
      final response = await ApiClient().dio.get(
        '/api/medicine-trace-codes/lookup',
        queryParameters: {'trace_code': code},
      );
      final data = Map<String, dynamic>.from(response.data as Map);
      if (data['prescription_id'] != null &&
          int.tryParse(data['prescription_id'].toString()) !=
              _selectedPrescriptionId) {
        throw DioException(
          requestOptions: response.requestOptions,
          message: '该追溯码已绑定其他处方',
        );
      }
      if (data['status']?.toString() == 'scanned_confirm') {
        throw DioException(
          requestOptions: response.requestOptions,
          message: '本药品已完成全部扫描',
        );
      }
      final entry = _entryFromData(
        data,
        code,
        action: data['status']?.toString() == 'scanned_outbound'
            ? '待确认接收'
            : '待确认出库',
      );
      setState(() {
        _history.removeWhere((item) => item.traceCode == entry.traceCode);
        _history.insert(0, entry);
        _searchResult = entry;
      });
      SystemSound.play(SystemSoundType.click);
      HapticFeedback.lightImpact();
      _showMessage('扫码成功，请确认后录入数据库', false);
    } on DioException catch (error) {
      final match = error.response?.data;
      if (match is Map &&
          match['can_import'] == true &&
          match['medicine_id'] != null) {
        final entry = _TraceEntry(
          traceCode: code,
          medicineName: match['medicine_name']?.toString() ?? '未命名药品',
          status: 'pending',
          action: '本药品扫码入库',
          time: _now(),
          isImport: true,
          message: '追溯码未入库，已按前 7 位匹配药品类别',
        );
        setState(() {
          _history.removeWhere((item) => item.traceCode == code);
          _history.insert(0, entry);
          _searchResult = entry;
        });
        SystemSound.play(SystemSoundType.click);
        _showMessage('已匹配药品类别，请确认扫码入库', false);
        return;
      }
      final message = _errorMessage(error, '扫码失败，请重试');
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

  Future<void> _confirmEntry(_TraceEntry entry) async {
    if (_confirmingCode.isNotEmpty) return;
    if (!entry.isImport && _selectedPrescriptionId == null) {
      _showMessage('请先选择当前处方', true);
      return;
    }
    setState(() => _confirmingCode = entry.traceCode);
    try {
      final response = entry.isImport
          ? await ApiClient().dio.post(
              '/api/medicine-trace-codes/register-by-prefix',
              data: {'trace_code': entry.traceCode},
            )
          : await ApiClient().dio.post(
              '/api/medicine-trace-codes/scan-by-code',
              data: {
                'trace_code': entry.traceCode,
                'prescription_id': _selectedPrescriptionId,
              },
            );
      final data = Map<String, dynamic>.from(response.data as Map);
      final updatedEntry = _entryFromData(
        data,
        entry.traceCode,
        action: data['action']?.toString() ?? '已录入',
      );
      setState(() {
        _history.removeWhere((item) => item.traceCode == entry.traceCode);
        _searchResult = updatedEntry;
      });
      HapticFeedback.mediumImpact();
      _showMessage(
        entry.isImport ? '追溯码已确认入库' : '${updatedEntry.action}已确认并录入数据库',
        false,
      );
      if (!entry.isImport) await _loadPrescriptions();
    } on DioException catch (error) {
      HapticFeedback.heavyImpact();
      _showMessage(_errorMessage(error, '确认录入失败，请重试'), true);
    } finally {
      if (mounted) setState(() => _confirmingCode = '');
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
                    '扫码后先暂存药品信息，确认后才会录入数据库。',
                    style: TextStyle(color: Colors.grey, fontSize: 13),
                  ),
                ),
                GlassCard(
                  margin: EdgeInsets.zero,
                  borderRadius: 24,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        '当前处理处方',
                        style: TextStyle(fontWeight: FontWeight.w800),
                      ),
                      const SizedBox(height: 10),
                      if (_prescriptionsLoading)
                        const Center(child: CircularProgressIndicator())
                      else if (_prescriptions.isEmpty)
                        const Text(
                          '暂无需要扫码的处方',
                          style: TextStyle(color: Colors.grey),
                        )
                      else
                        DropdownButtonFormField<int>(
                          key: ValueKey(_selectedPrescriptionId),
                          initialValue: _selectedPrescriptionId,
                          isExpanded: true,
                          decoration: const InputDecoration(
                            prefixIcon: Icon(CupertinoIcons.doc_text),
                            labelText: '选择处方',
                          ),
                          items: _prescriptions.map((item) {
                            final prescription = Map<String, dynamic>.from(
                              item as Map,
                            );
                            final id = prescription['id'] as int;
                            final code =
                                prescription['prescription_code']?.toString() ??
                                '#$id';
                            final patient =
                                prescription['patient_name']?.toString() ??
                                '未知病人';
                            return DropdownMenuItem<int>(
                              value: id,
                              child: Text('$code · $patient'),
                            );
                          }).toList(),
                          onChanged: (value) =>
                              unawaited(_selectPrescription(value)),
                        ),
                      if (_prescriptionDetail?['items'] is List) ...[
                        const SizedBox(height: 12),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: (_prescriptionDetail!['items'] as List).map((
                            item,
                          ) {
                            final detail = Map<String, dynamic>.from(
                              item as Map,
                            );
                            final bound =
                                (detail['trace_codes'] as List?)?.length ?? 0;
                            final quantity = detail['quantity'] ?? 0;
                            return Chip(
                              label: Text(
                                '${detail['medicine_name'] ?? '药品'} $bound/$quantity${detail['unit'] ?? ''}',
                              ),
                            );
                          }).toList(),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 12),
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
                        decoration: InputDecoration(
                          prefixIcon: const Icon(CupertinoIcons.barcode),
                          hintText: _selectedPrescriptionId == null
                              ? '请先选择当前处方'
                              : '输入或扫描药品追溯码',
                          labelText: '扫码输入',
                        ),
                      ),
                      const SizedBox(height: 12),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            _processing ? '正在读取药品信息…' : '扫码不会直接写入数据库',
                            style: const TextStyle(
                              color: Colors.grey,
                              fontSize: 11,
                            ),
                          ),
                          const Text(
                            '确认后录入',
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
                            '待确认扫码',
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
                                  '暂无待确认药品',
                                  style: TextStyle(
                                    fontWeight: FontWeight.w700,
                                    color: Colors.grey,
                                  ),
                                ),
                                SizedBox(height: 3),
                                Text(
                                  '扫描成功后，药品信息会暂存在这里',
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
                if (entry.message != null) ...[
                  const SizedBox(height: 3),
                  Text(
                    entry.message!,
                    style: const TextStyle(color: Colors.orange, fontSize: 11),
                  ),
                ],
              ],
            ),
          ),
          _StatusPill(label: _statusLabel(entry.status), color: color),
        ],
      ),
    );
  }

  Widget _buildHistoryEntry(_TraceEntry entry, int index, bool isDark) {
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
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 3),
                Text(
                  entry.time,
                  style: const TextStyle(color: Colors.grey, fontSize: 11),
                ),
                if (entry.message != null) ...[
                  const SizedBox(height: 3),
                  Text(
                    entry.message!,
                    style: const TextStyle(color: Colors.orange, fontSize: 11),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: 8),
          SizedBox(
            width: 88,
            child: FilledButton(
              onPressed: _confirmingCode.isEmpty
                  ? () => unawaited(_confirmEntry(entry))
                  : null,
              style: FilledButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 9),
                backgroundColor: const Color(0xFF00897B),
              ),
              child: Text(
                _confirmingCode == entry.traceCode
                    ? '录入中…'
                    : entry.isImport
                    ? '确认扫码入库'
                    : entry.status == 'scanned_outbound'
                    ? '确认接收'
                    : '确认出库',
                style: const TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                ),
              ),
            ),
          ),
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
