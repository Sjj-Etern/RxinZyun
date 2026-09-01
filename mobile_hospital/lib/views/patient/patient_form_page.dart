import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'dart:math';
import 'package:dio/dio.dart';
import 'package:his_mobile/core/network/api_client.dart';
import 'package:his_mobile/data/models/patient_model.dart';
import 'package:his_mobile/core/widgets/animated_scale_button.dart';

class PatientFormPage extends StatefulWidget {
  final PatientModel? patient; // 如果有值则为“编辑”，无值则为“新增”

  const PatientFormPage({super.key, this.patient});

  @override
  State<PatientFormPage> createState() => _PatientFormPageState();
}

class _PatientFormPageState extends State<PatientFormPage> {
  final _formKey = GlobalKey<FormState>();
  
  final _nameController = TextEditingController();
  final _ageController = TextEditingController();
  final _medRecordController = TextEditingController();
  final _phoneController = TextEditingController();
  
  String _gender = '男'; // 默认男
  bool _isLoading = false;

  bool get isEdit => widget.patient != null;

  @override
  void initState() {
    super.initState();
    if (isEdit) {
      final p = widget.patient!;
      _nameController.text = p.name;
      _ageController.text = p.age.toString();
      _medRecordController.text = p.medicalRecordNo;
      _phoneController.text = p.phone ?? '';
      _gender = p.gender;
    } else {
      _generateMedicalRecordNo(); // 自动生成一个病历号，极大提升医生录入体验
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _ageController.dispose();
    _medRecordController.dispose();
    _phoneController.dispose();
    super.dispose();
  }

  // 自动生成病历号（格式：HZ + 年月日时分秒 + 3位随机数）
  void _generateMedicalRecordNo() {
    final now = DateTime.now();
    final random = Random().nextInt(900) + 100; // 100-999
    final dateStr = '${now.year}${now.month.toString().padLeft(2, '0')}${now.day.toString().padLeft(2, '0')}';
    _medRecordController.text = 'HZ$dateStr$random';
  }

  Future<void> _submitForm() async {
    if (!_formKey.currentState!.validate()) {
      HapticFeedback.heavyImpact();
      return;
    }

    HapticFeedback.mediumImpact();
    setState(() {
      _isLoading = true;
    });

    final payload = {
      'name': _nameController.text.trim(),
      'age': int.parse(_ageController.text),
      'gender': _gender,
      'medical_record_no': _medRecordController.text.trim(),
      'id_card': _medRecordController.text.trim(),
      'phone': _phoneController.text.trim(),
    };

    try {
      Response response;
      if (isEdit) {
        response = await ApiClient().dio.put(
          '/api/patients/${widget.patient!.id}',
          data: payload,
        );
      } else {
        response = await ApiClient().dio.post(
          '/api/patients',
          data: payload,
        );
      }

      if ((response.statusCode == 200 || response.statusCode == 201) && mounted) {
        HapticFeedback.mediumImpact();
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(isEdit ? '患者信息已更新' : '成功录入新患者'), 
            backgroundColor: const Color(0xFF30D158),
          ),
        );
        Navigator.pop(context, true); // 返回并通知刷新
      }
    } on DioException catch (e) {
      String errStr = '操作失败';
      if (e.response != null && e.response!.data != null) {
        errStr = e.response!.data['error']?.toString() ?? errStr;
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(errStr), backgroundColor: Colors.redAccent),
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

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: Text(isEdit ? '编辑患者信息' : '录入新患者'),
        backgroundColor: Colors.transparent,
        elevation: 0,
      ),
      body: Container(
        height: double.infinity,
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
            ? const Center(child: CircularProgressIndicator(color: Color(0xFF009688)))
            : SafeArea(
                child: SingleChildScrollView(
                  padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // 姓名
                        const Text('基本资料', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Colors.grey)),
                        const SizedBox(height: 10),
                        _buildInputField(
                          controller: _nameController,
                          labelText: '患者姓名',
                          placeholder: '请输入姓名',
                          icon: CupertinoIcons.person,
                          isDark: isDark,
                          validator: (value) {
                            if (value == null || value.trim().isEmpty) {
                              return '请输入患者姓名';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 18),

                        // 年龄与性别同行
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              flex: 4,
                              child: _buildInputField(
                                controller: _ageController,
                                labelText: '年龄',
                                placeholder: '输入年龄',
                                icon: CupertinoIcons.calendar,
                                isDark: isDark,
                                keyboardType: TextInputType.number,
                                validator: (value) {
                                  if (value == null || value.isEmpty) {
                                    return '请输入年龄';
                                  }
                                  final age = int.tryParse(value);
                                  if (age == null || age <= 0 || age > 130) {
                                    return '无效年龄';
                                  }
                                  return null;
                                },
                              ),
                            ),
                            const SizedBox(width: 16),
                            Expanded(
                              flex: 5,
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  const Text('  性别', style: TextStyle(fontSize: 11, color: Colors.grey, fontWeight: FontWeight.bold)),
                                  const SizedBox(height: 6),
                                  Container(
                                    height: 48,
                                    alignment: Alignment.center,
                                    decoration: BoxDecoration(
                                      color: isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.04),
                                      borderRadius: BorderRadius.circular(16),
                                    ),
                                    child: CupertinoSegmentedControl<String>(
                                      groupValue: _gender,
                                      selectedColor: const Color(0xFF00796B),
                                      borderColor: Colors.transparent,
                                      unselectedColor: Colors.transparent,
                                      pressedColor: const Color(0xFF00796B).withValues(alpha: 0.2),
                                      children: const {
                                        '男': Padding(padding: EdgeInsets.symmetric(horizontal: 16), child: Text('男', style: TextStyle(fontSize: 13))),
                                        '女': Padding(padding: EdgeInsets.symmetric(horizontal: 16), child: Text('女', style: TextStyle(fontSize: 13))),
                                      },
                                      onValueChanged: (val) {
                                        setState(() {
                                          _gender = val;
                                        });
                                      },
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 24),

                        // 病历号
                        const Text('医疗档案', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: Colors.grey)),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: _buildInputField(
                                controller: _medRecordController,
                                labelText: '病历号',
                                placeholder: '请输入病历号',
                                icon: CupertinoIcons.doc_plaintext,
                                isDark: isDark,
                                enabled: !isEdit,
                                validator: (value) {
                                  if (value == null || value.trim().isEmpty) {
                                    return '请输入或生成病历号';
                                  }
                                  return null;
                                },
                              ),
                            ),
                            if (!isEdit) ...[
                              const SizedBox(width: 12),
                              AnimatedScaleButton(
                                onTap: _generateMedicalRecordNo,
                                child: Container(
                                  height: 48,
                                  width: 48,
                                  decoration: BoxDecoration(
                                    color: const Color(0xFF00796B).withValues(alpha: 0.12),
                                    borderRadius: BorderRadius.circular(16),
                                  ),
                                  child: const Icon(CupertinoIcons.refresh_thick, color: Color(0xFF00796B), size: 18),
                                ),
                              )
                            ],
                          ],
                        ),
                        const SizedBox(height: 18),

                        // 手机号
                        _buildInputField(
                          controller: _phoneController,
                          labelText: '手机号码 (选填)',
                          placeholder: '主要联系电话',
                          icon: CupertinoIcons.phone,
                          isDark: isDark,
                          keyboardType: TextInputType.phone,
                          validator: (value) {
                            if (value != null && value.isNotEmpty) {
                              if (!RegExp(r'^1[3-9]\d{9}$').hasMatch(value)) {
                                return '请输入正确的手机号码格式';
                              }
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 40),

                        // 提交按钮
                        AnimatedScaleButton(
                          onTap: _submitForm,
                          child: Container(
                            height: 52,
                            decoration: BoxDecoration(
                              gradient: const LinearGradient(
                                colors: [Color(0xFF009688), Color(0xFF00796B)],
                              ),
                              borderRadius: BorderRadius.circular(20),
                              boxShadow: [
                                BoxShadow(
                                  color: const Color(0xFF009688).withValues(alpha: 0.25),
                                  blurRadius: 12,
                                  offset: const Offset(0, 4),
                                )
                              ],
                            ),
                            alignment: Alignment.center,
                            child: Text(
                              isEdit ? '保存修改' : '确认录入',
                              style: const TextStyle(
                                color: Colors.white,
                                fontWeight: FontWeight.w900,
                                fontSize: 15,
                                letterSpacing: 1.5,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
      ),
    );
  }

  // 苹果风格输入外框组件
  Widget _buildInputField({
    required TextEditingController controller,
    required String labelText,
    required String placeholder,
    required IconData icon,
    required bool isDark,
    bool enabled = true,
    TextInputType keyboardType = TextInputType.text,
    String? Function(String?)? validator,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('  $labelText', style: const TextStyle(fontSize: 11, color: Colors.grey, fontWeight: FontWeight.bold)),
        const SizedBox(height: 6),
        Container(
          decoration: BoxDecoration(
            color: enabled 
                ? (isDark ? Colors.white.withValues(alpha: 0.08) : Colors.black.withValues(alpha: 0.04))
                : (isDark ? Colors.white.withValues(alpha: 0.02) : Colors.black.withValues(alpha: 0.02)),
            borderRadius: BorderRadius.circular(16),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 12),
          child: TextFormField(
            controller: controller,
            enabled: enabled,
            keyboardType: keyboardType,
            style: TextStyle(
              color: enabled 
                  ? (isDark ? Colors.white : Colors.black87)
                  : Colors.grey,
              fontSize: 14,
            ),
            decoration: InputDecoration(
              border: InputBorder.none,
              enabledBorder: InputBorder.none,
              focusedBorder: InputBorder.none,
              errorBorder: InputBorder.none,
              focusedErrorBorder: InputBorder.none,
              filled: false,
              prefixIcon: Icon(icon, color: isDark ? Colors.white60 : Colors.black45, size: 16),
              hintText: placeholder,
              hintStyle: const TextStyle(fontSize: 12, color: Colors.grey),
            ),
            validator: validator,
          ),
        ),
      ],
    );
  }
}
