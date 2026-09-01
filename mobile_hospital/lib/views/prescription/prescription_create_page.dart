import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:dio/dio.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/data/models/patient_model.dart';
import 'package:his_mobile/data/models/medicine_model.dart';
import 'package:his_mobile/core/theme/glass_card.dart';
import 'package:his_mobile/core/widgets/animated_scale_button.dart';

class PrescriptionCreatePage extends StatefulWidget {
  const PrescriptionCreatePage({super.key});

  @override
  State<PrescriptionCreatePage> createState() => _PrescriptionCreatePageState();
}

class _PrescriptionCreatePageState extends State<PrescriptionCreatePage> {
  final _formKey = GlobalKey<FormState>();

  // 处方头信息
  String _prescriptionType = '普通';
  String _paymentType = '医保';
  final _departmentController = TextEditingController(text: '普通内科');
  final _bedNoController = TextEditingController();
  final _diagnosisController = TextEditingController();
  final _noteController = TextEditingController();

  PatientModel? _selectedPatient;
  final List<Map<String, dynamic>> _selectedItems = []; // 包含 medicine, dosage, usage, frequency, days, quantity, trace_code, note
  bool _isLoading = false;

  final List<String> _prescriptionTypes = ['普通', '急诊', '儿科', '麻醉精一', '精二'];
  final List<String> _paymentTypes = ['自费', '医保', '公费', '部分自费'];
  final List<String> _usageMethods = ['口服', '外用', '注射', '含服', '吸入'];
  final List<String> _frequencies = ['每日1次', '每日2次', '每日3次', '每日4次', '睡前1次', '必要时'];

  @override
  void dispose() {
    _departmentController.dispose();
    _bedNoController.dispose();
    _diagnosisController.dispose();
    _noteController.dispose();
    super.dispose();
  }

  // 弹出选择患者底部抽屉 (Cupertino style search sheet)
  void _showPatientSelector() async {
    final List<PatientModel> patientList = [];
    bool listLoading = false;
    String searchKeyword = '';
    final isDark = Theme.of(context).brightness == Brightness.dark;
    
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: isDark ? const Color(0xFF101424) : Colors.white,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            
            Future<void> fetchPatients() async {
              setSheetState(() => listLoading = true);
              try {
                final res = await ApiClient().dio.get('/api/patients', queryParameters: {'keyword': searchKeyword, 'pageSize': 20});
                final list = res.data['list'] as List? ?? [];
                setSheetState(() {
                  patientList.clear();
                  patientList.addAll(list.map((p) => PatientModel.fromJson(p as Map<String, dynamic>)));
                });
              } catch (_) {}
              setSheetState(() => listLoading = false);
            }

            return Container(
              height: MediaQuery.of(context).size.height * 0.75,
              padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.of(context).viewInsets.bottom + 20),
              child: Column(
                children: [
                  Container(
                    width: 40,
                    height: 5,
                    decoration: BoxDecoration(color: Colors.grey.shade400, borderRadius: BorderRadius.circular(10)),
                  ),
                  const SizedBox(height: 16),
                  const Text('选择就诊患者', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900)),
                  const SizedBox(height: 16),
                  // 苹果极简搜索框
                  Container(
                    decoration: BoxDecoration(
                      color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.03),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: isDark ? Colors.white10 : Colors.black12),
                    ),
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: TextField(
                      style: TextStyle(color: isDark ? Colors.white : Colors.black87),
                      decoration: InputDecoration(
                        border: InputBorder.none,
                        hintText: '搜索患者姓名或手机号',
                        hintStyle: const TextStyle(fontSize: 12, color: Colors.grey),
                        prefixIcon: Icon(CupertinoIcons.search, size: 18, color: isDark ? Colors.white60 : Colors.black45),
                      ),
                      onSubmitted: (val) {
                        searchKeyword = val.trim();
                        fetchPatients();
                      },
                    ),
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: listLoading
                        ? const Center(child: CircularProgressIndicator(color: Color(0xFF00796B)))
                        : patientList.isEmpty
                            ? const Center(child: Text('输入关键字并按回车搜索患者', style: TextStyle(color: Colors.grey, fontSize: 13)))
                            : ListView.builder(
                                itemCount: patientList.length,
                                itemBuilder: (context, index) {
                                  final p = patientList[index];
                                  return ListTile(
                                    contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                    leading: CircleAvatar(
                                      backgroundColor: p.gender == '男' 
                                          ? const Color(0xFF007AFF).withValues(alpha: 0.1) 
                                          : const Color(0xFFFF2D55).withValues(alpha: 0.1),
                                      child: Icon(
                                        CupertinoIcons.person_fill, 
                                        color: p.gender == '男' ? const Color(0xFF007AFF) : const Color(0xFFFF2D55),
                                        size: 16,
                                      ),
                                    ),
                                    title: Text(p.name, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
                                    subtitle: Text('病历号: ${p.medicalRecordNo} | 年龄: ${p.age}', style: const TextStyle(fontSize: 11)),
                                    trailing: const Icon(CupertinoIcons.chevron_right, size: 14, color: Colors.grey),
                                    onTap: () {
                                      setState(() {
                                        _selectedPatient = p;
                                      });
                                      HapticFeedback.mediumImpact();
                                      Navigator.pop(context);
                                    },
                                  );
                                },
                              ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  void _showErrorSnackbar(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg), backgroundColor: Colors.redAccent));
  }

  // 弹出选择药品底部抽屉
  void _showMedicineSelector() {
    final List<MedicineModel> medList = [];
    bool listLoading = false;
    String searchKeyword = '';
    final isDark = Theme.of(context).brightness == Brightness.dark;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: isDark ? const Color(0xFF101424) : Colors.white,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(24))),
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            
            Future<void> fetchMedicines() async {
              setSheetState(() => listLoading = true);
              try {
                final res = await ApiClient().dio.get('/api/medicines', queryParameters: {'keyword': searchKeyword, 'pageSize': 20});
                final list = res.data['list'] as List? ?? [];
                setSheetState(() {
                  medList.clear();
                  medList.addAll(list.map((m) => MedicineModel.fromJson(m as Map<String, dynamic>)));
                });
              } catch (_) {}
              setSheetState(() => listLoading = false);
            }

            return Container(
              height: MediaQuery.of(context).size.height * 0.75,
              padding: EdgeInsets.fromLTRB(20, 20, 20, MediaQuery.of(context).viewInsets.bottom + 20),
              child: Column(
                children: [
                  Container(
                    width: 40,
                    height: 5,
                    decoration: BoxDecoration(color: Colors.grey.shade400, borderRadius: BorderRadius.circular(10)),
                  ),
                  const SizedBox(height: 16),
                  const Text('选择处方药品', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900)),
                  const SizedBox(height: 16),
                  // 苹果极简搜索框
                  Container(
                    decoration: BoxDecoration(
                      color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.03),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: isDark ? Colors.white10 : Colors.black12),
                    ),
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    child: TextField(
                      style: TextStyle(color: isDark ? Colors.white : Colors.black87),
                      decoration: InputDecoration(
                        border: InputBorder.none,
                        hintText: '搜索药品名称或厂商',
                        hintStyle: const TextStyle(fontSize: 12, color: Colors.grey),
                        prefixIcon: Icon(CupertinoIcons.search, size: 18, color: isDark ? Colors.white60 : Colors.black45),
                      ),
                      onSubmitted: (val) {
                        searchKeyword = val.trim();
                        fetchMedicines();
                      },
                    ),
                  ),
                  const SizedBox(height: 16),
                  Expanded(
                    child: listLoading
                        ? const Center(child: CircularProgressIndicator(color: Color(0xFF00796B)))
                        : medList.isEmpty
                            ? const Center(child: Text('输入关键字并回车搜索药品', style: TextStyle(color: Colors.grey, fontSize: 13)))
                            : ListView.builder(
                                itemCount: medList.length,
                                itemBuilder: (context, index) {
                                  final m = medList[index];
                                  return ListTile(
                                    contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                    leading: CircleAvatar(
                                      backgroundColor: const Color(0xFF00796B).withValues(alpha: 0.1),
                                      child: const Icon(CupertinoIcons.bandage, color: Color(0xFF00796B), size: 16),
                                    ),
                                    title: Text(m.name, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
                                    subtitle: Text('规格: ${m.specification ?? "无"} | 库存: ${m.stock}', style: const TextStyle(fontSize: 11)),
                                    trailing: Text('¥${m.price.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF00796B))),
                                    onTap: () {
                                      Navigator.pop(context);
                                      if (_selectedItems.any((item) => item['medicine'].id == m.id)) {
                                        _showErrorSnackbar('处方中已包含此药品');
                                        return;
                                      }
                                      _showMedicineFormDialog(m);
                                    },
                                  );
                                },
                              ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  // 配置单个药品的具体用量、追溯码等 (Cupertino Form Dialogue)
  void _showMedicineFormDialog(MedicineModel medicine, {String traceCode = ''}) {
    final formKey = GlobalKey<FormState>();
    final dosageController = TextEditingController(text: '1片/次');
    final daysController = TextEditingController(text: '3');
    final quantityController = TextEditingController(text: '1');
    final traceController = TextEditingController(text: traceCode);
    final noteController = TextEditingController();

    String usageMethod = '口服';
    String frequency = '每日3次';
    final isDark = Theme.of(context).brightness == Brightness.dark;

    showCupertinoDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            return CupertinoAlertDialog(
              title: Text('配置 [${medicine.name}] 用量'),
              content: Material(
                color: Colors.transparent,
                child: SingleChildScrollView(
                  padding: const EdgeInsets.only(top: 12.0),
                  child: Form(
                    key: formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // 用量
                        _buildDialogInputField(
                          controller: dosageController,
                          labelText: '单次剂量',
                          placeholder: '如: 1片/次',
                          isDark: isDark,
                          validator: (v) => v!.isEmpty ? '必填' : null,
                        ),
                        const SizedBox(height: 12),
                        
                        // 用法 & 频次 同行
                        Row(
                          children: [
                            Expanded(
                              child: _buildDialogDropdownField<String>(
                                value: usageMethod,
                                labelText: '用法',
                                items: _usageMethods.map((u) => DropdownMenuItem(value: u, child: Text(u, style: const TextStyle(fontSize: 13)))).toList(),
                                onChanged: (v) => setDialogState(() => usageMethod = v!),
                                isDark: isDark,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: _buildDialogDropdownField<String>(
                                value: frequency,
                                labelText: '频次',
                                items: _frequencies.map((f) => DropdownMenuItem(value: f, child: Text(f, style: const TextStyle(fontSize: 13)))).toList(),
                                onChanged: (v) => setDialogState(() => frequency = v!),
                                isDark: isDark,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        
                        // 天数 & 数量
                        Row(
                          children: [
                            Expanded(
                              child: _buildDialogInputField(
                                controller: daysController,
                                labelText: '开药天数',
                                placeholder: '天数',
                                keyboardType: TextInputType.number,
                                isDark: isDark,
                                validator: (v) => int.tryParse(v ?? '') == null ? '整数' : null,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: _buildDialogInputField(
                                controller: quantityController,
                                labelText: '开药总量',
                                placeholder: '数量',
                                keyboardType: TextInputType.number,
                                isDark: isDark,
                                validator: (v) => int.tryParse(v ?? '') == null ? '整数' : null,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        
                        _buildDialogInputField(
                          controller: traceController,
                          labelText: '20位追溯码',
                          placeholder: '请输入药品追溯码',
                          isDark: isDark,
                          validator: (v) => v!.trim().isEmpty ? '追溯码必填' : null,
                        ),
                        const SizedBox(height: 12),
                        
                        _buildDialogInputField(
                          controller: noteController,
                          labelText: '备注说明',
                          placeholder: '选填说明',
                          isDark: isDark,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              actions: [
                CupertinoDialogAction(
                  isDestructiveAction: true,
                  onPressed: () => Navigator.pop(context),
                  child: const Text('取消'),
                ),
                CupertinoDialogAction(
                  isDefaultAction: true,
                  onPressed: () {
                    if (!formKey.currentState!.validate()) {
                      HapticFeedback.heavyImpact();
                      return;
                    }
                    
                    setState(() {
                      _selectedItems.add({
                        'medicine': medicine,
                        'dosage': dosageController.text.trim(),
                        'usage_method': usageMethod,
                        'frequency': frequency,
                        'days': int.parse(daysController.text),
                        'quantity': int.parse(quantityController.text),
                        'trace_code': traceController.text.trim(),
                        'note': noteController.text.trim(),
                      });
                    });
                    HapticFeedback.mediumImpact();
                    Navigator.pop(context);
                  },
                  child: const Text('确认添加'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  // 计算处方总价
  double _calculateTotalAmount() {
    double total = 0;
    for (var item in _selectedItems) {
      final med = item['medicine'] as MedicineModel;
      final qty = item['quantity'] as int;
      total += med.price * qty;
    }
    return total;
  }

  // 提交处方到 HIS 后端
  Future<void> _submitPrescription() async {
    if (_selectedPatient == null) {
      _showErrorSnackbar('请先选择就诊患者');
      return;
    }
    if (_diagnosisController.text.trim().isEmpty) {
      _showErrorSnackbar('请输入临床诊断结论');
      return;
    }
    if (_selectedItems.isEmpty) {
      _showErrorSnackbar('请至少配置一种开药明细');
      return;
    }

    setState(() {
      _isLoading = true;
    });

    final payload = {
      'patient_id': _selectedPatient!.id,
      'prescription_type': _prescriptionType,
      'payment_type': _paymentType,
      'medical_record_no': _selectedPatient!.medicalRecordNo,
      'department': _departmentController.text.trim(),
      'bed_no': _bedNoController.text.trim(),
      'diagnosis': _diagnosisController.text.trim(),
      'note': _noteController.text.trim(),
      'items': _selectedItems.map((item) {
        final med = item['medicine'] as MedicineModel;
        return {
          'medicine_id': med.id,
          'dosage': item['dosage'],
          'usage_method': item['usage_method'],
          'frequency': item['frequency'],
          'days': item['days'],
          'quantity': item['quantity'],
          'trace_code': item['trace_code'],
          'note': item['note'],
        };
      }).toList(),
    };

    try {
      final response = await ApiClient().dio.post('/api/prescriptions', data: payload);
      if (response.statusCode == 201 && mounted) {
        final code = response.data['prescription_code'];
        HapticFeedback.mediumImpact();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('处方已创建并进入发药环节！编号: $code'), backgroundColor: const Color(0xFF30D158)),
        );
        Navigator.pop(context, true); // 成功返回
      }
    } on DioException catch (e) {
      final err = e.response?.data?['error']?.toString() ?? '处方提交失败';
      _showErrorSnackbar(err);
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('开具新处方'),
        backgroundColor: Colors.transparent,
        elevation: 0,
      ),
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: isDark
                ? [const Color(0xFF090C15), const Color(0xFF0B1B2A), const Color(0xFF141221)]
                : [const Color(0xFFEAF6FF), const Color(0xFFEDFDF8), const Color(0xFFFFF2F7)],
          ),
        ),
        child: _isLoading
            ? const Center(child: CircularProgressIndicator(color: Color(0xFF00796B)))
            : SafeArea(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.fromLTRB(20.0, 16.0, 20.0, 120.0), // 留够底部空间防止导航栏遮挡
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // 板块一：患者档案
                        GlassCard(
                          margin: const EdgeInsets.only(bottom: 16),
                          padding: const EdgeInsets.all(20.0),
                          borderRadius: 24,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('患者就诊档案', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Colors.grey)),
                              const SizedBox(height: 16),
                              _selectedPatient == null
                                  ? Center(
                                      child: AnimatedScaleButton(
                                        onTap: _showPatientSelector,
                                        child: Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                                          decoration: BoxDecoration(
                                            color: const Color(0xFF00796B).withValues(alpha: 0.15),
                                            borderRadius: BorderRadius.circular(16),
                                          ),
                                          child: const Row(
                                            mainAxisSize: MainAxisSize.min,
                                            children: [
                                              Icon(CupertinoIcons.person_add, color: Color(0xFF00796B), size: 18),
                                              SizedBox(width: 8),
                                              Text('选择就诊患者', style: TextStyle(color: Color(0xFF00796B), fontWeight: FontWeight.w900)),
                                            ],
                                          ),
                                        ),
                                      ),
                                    )
                                  : Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                '${_selectedPatient!.name} (${_selectedPatient!.gender} · ${_selectedPatient!.age}岁)',
                                                style: TextStyle(
                                                  fontWeight: FontWeight.w900, 
                                                  fontSize: 17,
                                                  color: isDark ? Colors.white : const Color(0xFF1E293B),
                                                ),
                                              ),
                                              const SizedBox(height: 4),
                                              Text(
                                                '病历号: ${_selectedPatient!.medicalRecordNo}', 
                                                style: const TextStyle(fontSize: 13, color: Colors.grey),
                                              ),
                                            ],
                                          ),
                                        ),
                                        AnimatedScaleButton(
                                          onTap: _showPatientSelector,
                                          child: Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                                            decoration: BoxDecoration(
                                              color: const Color(0xFF00796B).withValues(alpha: 0.08),
                                              borderRadius: BorderRadius.circular(12),
                                            ),
                                            child: const Text('更换患者', style: TextStyle(color: Color(0xFF00796B), fontWeight: FontWeight.bold, fontSize: 13)),
                                          ),
                                        )
                                      ],
                                    ),
                            ],
                          ),
                        ),

                        // 板块二：处方属性
                        GlassCard(
                          margin: const EdgeInsets.only(bottom: 16),
                          padding: const EdgeInsets.all(20.0),
                          borderRadius: 24,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('处方属性', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Colors.grey)),
                              const SizedBox(height: 16),
                              Row(
                                children: [
                                  Expanded(
                                    child: _buildDropdownField<String>(
                                      value: _prescriptionType,
                                      labelText: '处方类型',
                                      icon: CupertinoIcons.doc_text,
                                      items: _prescriptionTypes.map((t) => DropdownMenuItem(value: t, child: Text(t, style: const TextStyle(fontSize: 13)))).toList(),
                                      onChanged: (v) => setState(() => _prescriptionType = v!),
                                      isDark: isDark,
                                    ),
                                  ),
                                  const SizedBox(width: 14),
                                  Expanded(
                                    child: _buildDropdownField<String>(
                                      value: _paymentType,
                                      labelText: '支付费别',
                                      icon: CupertinoIcons.money_yen_circle,
                                      items: _paymentTypes.map((t) => DropdownMenuItem(value: t, child: Text(t, style: const TextStyle(fontSize: 13)))).toList(),
                                      onChanged: (v) => setState(() => _paymentType = v!),
                                      isDark: isDark,
                                    ),
                                  ),
                                ],
                              ),
                              const SizedBox(height: 16),
                              Row(
                                children: [
                                  Expanded(
                                    child: _buildInputField(
                                      controller: _departmentController,
                                      labelText: '就诊科别',
                                      placeholder: '如: 内科',
                                      icon: CupertinoIcons.house,
                                      isDark: isDark,
                                    ),
                                  ),
                                  const SizedBox(width: 14),
                                  Expanded(
                                    child: _buildInputField(
                                      controller: _bedNoController,
                                      labelText: '床位号 (选填)',
                                      placeholder: '请输入床号',
                                      icon: CupertinoIcons.bed_double,
                                      isDark: isDark,
                                    ),
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),

                        // 板块三：临床诊断
                        GlassCard(
                          margin: const EdgeInsets.only(bottom: 16),
                          padding: const EdgeInsets.all(20.0),
                          borderRadius: 24,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('临床诊断结论', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Colors.grey)),
                              const SizedBox(height: 12),
                              Container(
                                decoration: BoxDecoration(
                                  color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.04),
                                  borderRadius: BorderRadius.circular(16),
                                ),
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                                child: TextFormField(
                                  controller: _diagnosisController,
                                  maxLines: 2,
                                  style: TextStyle(color: isDark ? Colors.white : Colors.black87, fontSize: 13),
                                  decoration: const InputDecoration(
                                    border: InputBorder.none,
                                    filled: false,
                                    enabledBorder: InputBorder.none,
                                    focusedBorder: InputBorder.none,
                                    errorBorder: InputBorder.none,
                                    focusedErrorBorder: InputBorder.none,
                                    hintText: '请输入本次就诊的临床诊断结论说明...',
                                    hintStyle: TextStyle(fontSize: 12, color: Colors.grey),
                                  ),
                                  validator: (v) => v!.trim().isEmpty ? '请输入临床诊断' : null,
                                ),
                              ),
                            ],
                          ),
                        ),

                        // 板块四：处方药品明细
                        GlassCard(
                          margin: const EdgeInsets.only(bottom: 16),
                          padding: const EdgeInsets.all(20.0),
                          borderRadius: 24,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  const Text('药品明细 (最多5种)', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Colors.grey)),
                                  AnimatedScaleButton(
                                    onTap: _showMedicineSelector,
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFF00796B).withValues(alpha: 0.08),
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: const Row(
                                        children: [
                                          Icon(CupertinoIcons.plus, color: Color(0xFF00796B), size: 14),
                                          SizedBox(width: 4),
                                          Text('添加药品', style: TextStyle(color: Color(0xFF00796B), fontWeight: FontWeight.bold, fontSize: 12)),
                                        ],
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                              const Divider(height: 24, color: Colors.black12),
                              _selectedItems.isEmpty
                                  ? const Center(
                                      child: Padding(
                                        padding: EdgeInsets.symmetric(vertical: 32.0),
                                        child: Text('请添加处方药品明细数据', style: TextStyle(color: Colors.grey, fontSize: 13)),
                                      ),
                                    )
                                  : ListView.builder(
                                      shrinkWrap: true,
                                      physics: const NeverScrollableScrollPhysics(),
                                      itemCount: _selectedItems.length,
                                      itemBuilder: (context, index) {
                                        final item = _selectedItems[index];
                                        final med = item['medicine'] as MedicineModel;
                                        
                                        return Container(
                                          margin: const EdgeInsets.only(bottom: 12),
                                          padding: const EdgeInsets.all(12),
                                          decoration: BoxDecoration(
                                            color: isDark ? Colors.white.withValues(alpha: 0.04) : Colors.white.withValues(alpha: 0.4),
                                            borderRadius: BorderRadius.circular(16),
                                            border: Border.all(color: isDark ? Colors.white10 : Colors.black12),
                                          ),
                                          child: Row(
                                            children: [
                                              Expanded(
                                                child: Column(
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    Text(
                                                      med.name,
                                                      style: TextStyle(
                                                        fontWeight: FontWeight.bold, 
                                                        fontSize: 14,
                                                        color: isDark ? Colors.white : const Color(0xFF1E293B),
                                                      ),
                                                    ),
                                                    const SizedBox(height: 6),
                                                    Text(
                                                      '剂量: ${item['dosage']} | 用法: ${item['usage_method']} | 频次: ${item['frequency']}\n疗程: ${item['days']}天 | 开药总量: ${item['quantity']} ${med.unit}\n追溯码: ${item['trace_code']}',
                                                      style: const TextStyle(fontSize: 11, color: Colors.grey, height: 1.4),
                                                    ),
                                                  ],
                                                ),
                                              ),
                                              const SizedBox(width: 8),
                                              AnimatedScaleButton(
                                                onTap: () {
                                                  setState(() {
                                                    _selectedItems.removeAt(index);
                                                  });
                                                },
                                                child: Container(
                                                  padding: const EdgeInsets.all(8),
                                                  decoration: BoxDecoration(
                                                    color: Colors.red.withValues(alpha: 0.1),
                                                    shape: BoxShape.circle,
                                                  ),
                                                  child: const Icon(CupertinoIcons.minus_circle, color: Colors.red, size: 18),
                                                ),
                                              ),
                                            ],
                                          ),
                                        );
                                      },
                                    ),
                            ],
                          ),
                        ),

                        // 备注说明
                        GlassCard(
                          margin: const EdgeInsets.only(bottom: 24),
                          padding: const EdgeInsets.all(20.0),
                          borderRadius: 24,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('处方医嘱备注', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Colors.grey)),
                              const SizedBox(height: 12),
                              _buildInputField(
                                controller: _noteController,
                                labelText: '留言给药师',
                                placeholder: '给药师的留言或特殊煎药要求...',
                                icon: CupertinoIcons.chat_bubble_text,
                                isDark: isDark,
                              ),
                            ],
                          ),
                        ),

                        // 统计与提交
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              '合计金额: ¥${_calculateTotalAmount().toStringAsFixed(2)}',
                              style: TextStyle(
                                fontSize: 16, 
                                fontWeight: FontWeight.w900, 
                                color: isDark ? const Color(0xFF4DB6AC) : const Color(0xFF00796B),
                              ),
                            ),
                            AnimatedScaleButton(
                              onTap: _submitPrescription,
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 14),
                                decoration: BoxDecoration(
                                  gradient: const LinearGradient(
                                    colors: [Color(0xFF009688), Color(0xFF00796B)],
                                  ),
                                  borderRadius: BorderRadius.circular(18),
                                  boxShadow: [
                                    BoxShadow(
                                      color: const Color(0xFF00796B).withValues(alpha: 0.25),
                                      blurRadius: 10,
                                      offset: const Offset(0, 4),
                                    )
                                  ],
                                ),
                                child: const Text(
                                  '提交处方',
                                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.w900, fontSize: 14, letterSpacing: 1.0),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
              ),
      ),
    );
  }

  // 苹果风格输入字段
  Widget _buildInputField({
    required TextEditingController controller,
    required String labelText,
    required String placeholder,
    required IconData icon,
    required bool isDark,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('  $labelText', style: const TextStyle(fontSize: 11, color: Colors.grey, fontWeight: FontWeight.bold)),
        const SizedBox(height: 6),
        Container(
          height: 48,
          decoration: BoxDecoration(
            color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.04),
            borderRadius: BorderRadius.circular(16),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Row(
            children: [
              Icon(icon, color: isDark ? Colors.white60 : Colors.black45, size: 16),
              const SizedBox(width: 8),
              Expanded(
                child: TextFormField(
                  controller: controller,
                  style: TextStyle(color: isDark ? Colors.white : Colors.black87, fontSize: 13),
                  decoration: InputDecoration(
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    errorBorder: InputBorder.none,
                    focusedErrorBorder: InputBorder.none,
                    filled: false,
                    hintText: placeholder,
                    hintStyle: const TextStyle(fontSize: 12, color: Colors.grey),
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // 苹果风格下拉选择字段
  Widget _buildDropdownField<T>({
    required T value,
    required String labelText,
    required IconData icon,
    required List<DropdownMenuItem<T>> items,
    required void Function(T?) onChanged,
    required bool isDark,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('  $labelText', style: const TextStyle(fontSize: 11, color: Colors.grey, fontWeight: FontWeight.bold)),
        const SizedBox(height: 6),
        Container(
          height: 48,
          decoration: BoxDecoration(
            color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.04),
            borderRadius: BorderRadius.circular(16),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: Row(
            children: [
              Icon(icon, color: isDark ? Colors.white60 : Colors.black45, size: 16),
              const SizedBox(width: 8),
              Expanded(
                child: DropdownButtonHideUnderline(
                  child: DropdownButton<T>(
                    value: value,
                    items: items,
                    onChanged: onChanged,
                    isExpanded: true,
                    style: TextStyle(color: isDark ? Colors.white : Colors.black87, fontSize: 13),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  // 对话框输入框
  Widget _buildDialogInputField({
    required TextEditingController controller,
    required String labelText,
    required String placeholder,
    required bool isDark,
    TextInputType keyboardType = TextInputType.text,
    String? Function(String?)? validator,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('  $labelText', style: const TextStyle(fontSize: 10, color: Colors.grey, fontWeight: FontWeight.bold)),
        const SizedBox(height: 4),
        Container(
          decoration: BoxDecoration(
            color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.04),
            borderRadius: BorderRadius.circular(10),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: TextFormField(
            controller: controller,
            keyboardType: keyboardType,
            style: TextStyle(color: isDark ? Colors.white : Colors.black87, fontSize: 13),
            decoration: InputDecoration(
              border: InputBorder.none,
              enabledBorder: InputBorder.none,
              focusedBorder: InputBorder.none,
              errorBorder: InputBorder.none,
              focusedErrorBorder: InputBorder.none,
              filled: false,
              hintText: placeholder,
              hintStyle: const TextStyle(fontSize: 12, color: Colors.grey),
              contentPadding: const EdgeInsets.symmetric(vertical: 8),
              errorStyle: const TextStyle(height: 0.8, fontSize: 10),
            ),
            validator: validator,
          ),
        ),
      ],
    );
  }

  // 对话框下拉选择器
  Widget _buildDialogDropdownField<T>({
    required T value,
    required String labelText,
    required List<DropdownMenuItem<T>> items,
    required void Function(T?) onChanged,
    required bool isDark,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('  $labelText', style: const TextStyle(fontSize: 10, color: Colors.grey, fontWeight: FontWeight.bold)),
        const SizedBox(height: 4),
        Container(
          height: 38,
          decoration: BoxDecoration(
            color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.04),
            borderRadius: BorderRadius.circular(10),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<T>(
              value: value,
              items: items,
              onChanged: onChanged,
              isExpanded: true,
              style: TextStyle(color: isDark ? Colors.white : Colors.black87, fontSize: 13),
            ),
          ),
        ),
      ],
    );
  }
}
