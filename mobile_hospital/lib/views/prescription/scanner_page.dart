import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

class ScannerPage extends StatefulWidget {
  const ScannerPage({super.key});

  @override
  State<ScannerPage> createState() => _ScannerPageState();
}

class _ScannerPageState extends State<ScannerPage> {
  final TextEditingController _codeController = TextEditingController();
  final FocusNode _focusNode = FocusNode();

  @override
  void dispose() {
    _codeController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _submit() {
    final code = _codeController.text.trim();
    if (code.isEmpty) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('请输入或扫描药品追溯码')));
      return;
    }
    Navigator.pop(context, code);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return Scaffold(
      appBar: AppBar(title: const Text('扫码输入追溯码')),
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
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: Card(
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(24),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Icon(
                          CupertinoIcons.barcode_viewfinder,
                          color: Color(0xFF00897B),
                          size: 48,
                        ),
                        const SizedBox(height: 16),
                        const Text(
                          '等待扫码输入',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          '请将光标放在输入框，扫码枪读取后按回车提交。',
                          style: TextStyle(color: Colors.grey, fontSize: 13),
                        ),
                        const SizedBox(height: 20),
                        TextField(
                          controller: _codeController,
                          focusNode: _focusNode,
                          autofocus: true,
                          textInputAction: TextInputAction.done,
                          onSubmitted: (_) => _submit(),
                          decoration: const InputDecoration(
                            prefixIcon: Icon(CupertinoIcons.barcode),
                            labelText: '追溯码',
                            hintText: '输入或扫描药品追溯码',
                          ),
                        ),
                        const SizedBox(height: 16),
                        SizedBox(
                          width: double.infinity,
                          child: FilledButton.icon(
                            onPressed: _submit,
                            icon: const Icon(CupertinoIcons.arrow_right),
                            label: const Text('提交扫码'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
