import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:camera/camera.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:his_mobile/core/network/api_client.dart';

class RealtimeFaceVerifyPage extends StatefulWidget {
  final int recordId;
  final String medicineName;
  final String robotCode;

  const RealtimeFaceVerifyPage({
    super.key,
    required this.recordId,
    required this.medicineName,
    required this.robotCode,
  });

  @override
  State<RealtimeFaceVerifyPage> createState() => _RealtimeFaceVerifyPageState();
}

class _RealtimeFaceVerifyPageState extends State<RealtimeFaceVerifyPage> {
  CameraController? _controller;
  Timer? _verifyTimer;
  Timer? _closeTimer;
  bool _initializing = true;
  bool _requesting = false;
  bool _succeeded = false;
  String _message = '正在连接前置摄像头…';

  @override
  void initState() {
    super.initState();
    _initializeCamera();
  }

  Future<void> _initializeCamera() async {
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) throw Exception('未检测到可用摄像头');
      final camera = cameras.firstWhere(
        (item) => item.lensDirection == CameraLensDirection.front,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        camera,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      _controller = controller;
      setState(() {
        _initializing = false;
        _message = '正在实时检测，请正对镜头并保持稳定';
      });
      await _verifyCurrentFrame();
      _verifyTimer = Timer.periodic(
        const Duration(milliseconds: 1200),
        (_) => _verifyCurrentFrame(),
      );
    } on CameraException catch (error) {
      _showCameraError(error.description ?? '无法打开摄像头，请检查相机权限');
    } catch (error) {
      _showCameraError(error.toString().replaceFirst('Exception: ', ''));
    }
  }

  void _showCameraError(String message) {
    if (!mounted) return;
    setState(() {
      _initializing = false;
      _message = message;
    });
  }

  Future<void> _verifyCurrentFrame() async {
    final controller = _controller;
    if (_requesting ||
        _succeeded ||
        controller == null ||
        !controller.value.isInitialized ||
        controller.value.isTakingPicture) {
      return;
    }
    _requesting = true;
    if (mounted) setState(() => _message = '正在检测并与已录入人脸比对…');
    try {
      final image = await controller.takePicture();
      final bytes = await image.readAsBytes();
      final response = await ApiClient().dio.post(
        '/api/delivery-records/${widget.recordId}/verify-and-unlock',
        data: {'face_image': 'data:image/jpeg;base64,${base64Encode(bytes)}'},
      );
      _verifyTimer?.cancel();
      if (!mounted) return;
      setState(() {
        _succeeded = true;
        _message = '人脸核验成功，机器人药箱已开锁\n摄像头将在 3 秒后自动关闭';
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            response.data['message']?.toString() ?? '人脸核验成功，机器人药箱已开锁',
          ),
        ),
      );
      _closeTimer = Timer(const Duration(seconds: 3), () {
        if (mounted) Navigator.pop(context, true);
      });
    } on DioException catch (error) {
      final message =
          error.response?.data?['error']?.toString() ?? '暂未识别到匹配人脸，请正对镜头';
      if (!mounted) return;
      setState(() => _message = message);
      if (message.contains('请先在身份认证')) _verifyTimer?.cancel();
    } on CameraException catch (error) {
      if (mounted) {
        setState(() => _message = error.description ?? '摄像头采集失败，正在重试');
      }
    } finally {
      _requesting = false;
    }
  }

  @override
  void dispose() {
    _verifyTimer?.cancel();
    _closeTimer?.cancel();
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    final ready = controller?.value.isInitialized == true;
    final statusColor = _succeeded
        ? const Color(0xFF15803D)
        : const Color(0xFF0369A1);
    return Scaffold(
      appBar: AppBar(
        title: const Text('实时人脸核验'),
        automaticallyImplyLeading: !_succeeded,
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${widget.medicineName} · ${widget.robotCode}',
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                  DecoratedBox(
                    decoration: BoxDecoration(
                      color: statusColor.withValues(alpha: .12),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 7,
                      ),
                      child: Text(
                        _succeeded
                            ? '核验成功'
                            : _initializing
                            ? '连接中'
                            : '实时检测中',
                        style: TextStyle(
                          color: statusColor,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: ColoredBox(
                    color: const Color(0xFF061923),
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        if (ready)
                          Transform(
                            alignment: Alignment.center,
                            transform: Matrix4.rotationY(math.pi),
                            child: CameraPreview(controller!),
                          )
                        else
                          const Center(child: CircularProgressIndicator()),
                        Center(
                          child: Container(
                            width: 210,
                            height: 285,
                            decoration: BoxDecoration(
                              border: Border.all(
                                color: _succeeded
                                    ? const Color(0xFF4ADE80)
                                    : Colors.white,
                                width: 2,
                              ),
                              borderRadius: BorderRadius.circular(110),
                            ),
                          ),
                        ),
                        Positioned(
                          left: 16,
                          right: 16,
                          bottom: 18,
                          child: DecoratedBox(
                            decoration: BoxDecoration(
                              color: Colors.black.withValues(alpha: .5),
                              borderRadius: BorderRadius.circular(14),
                            ),
                            child: Padding(
                              padding: const EdgeInsets.all(12),
                              child: Text(
                                _message,
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              const SizedBox(height: 14),
              const Text(
                '无需拍摄，摄像头会自动采集当前画面进行 OpenCV 人脸比对。',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey, fontSize: 12),
              ),
              const SizedBox(height: 12),
              OutlinedButton(
                onPressed: _succeeded
                    ? null
                    : () => Navigator.pop(context, false),
                child: const Text('取消核验'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
