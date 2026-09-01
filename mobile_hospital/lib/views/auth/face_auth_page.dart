import 'dart:convert';
import 'dart:math' as math;

import 'package:camera/camera.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:his_mobile/core/network/api_client.dart';

class FaceAuthPage extends StatefulWidget {
  const FaceAuthPage({super.key});

  @override
  State<FaceAuthPage> createState() => _FaceAuthPageState();
}

class _FaceAuthPageState extends State<FaceAuthPage> {
  CameraController? _controller;
  bool _enrolled = false;
  bool _loading = true;
  bool _cameraLoading = true;
  bool _saving = false;
  String _cameraMessage = '正在连接前置摄像头…';

  @override
  void initState() {
    super.initState();
    _loadEnrollment();
    _initializeCamera();
  }

  Future<void> _loadEnrollment() async {
    try {
      final response = await ApiClient().dio.get('/api/face-profiles');
      _enrolled = response.data['enrolled'] == true;
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
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
      setState(() {
        _controller = controller;
        _cameraLoading = false;
        _cameraMessage = '摄像头已就绪，请将脸部置于取景框内';
      });
    } on CameraException catch (error) {
      if (mounted) {
        setState(() {
          _cameraLoading = false;
          _cameraMessage = error.description ?? '无法打开摄像头，请检查相机权限';
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() {
          _cameraLoading = false;
          _cameraMessage = error.toString().replaceFirst('Exception: ', '');
        });
      }
    }
  }

  Future<void> _captureAndSave() async {
    final controller = _controller;
    if (controller == null ||
        !controller.value.isInitialized ||
        controller.value.isTakingPicture) {
      _show('摄像头正在连接，请稍候');
      return;
    }
    setState(() => _saving = true);
    try {
      final image = await controller.takePicture();
      final bytes = await image.readAsBytes();
      final response = await ApiClient().dio.put(
        '/api/face-profiles',
        data: {'face_image': 'data:image/jpeg;base64,${base64Encode(bytes)}'},
      );
      if (!mounted) return;
      setState(() {
        _enrolled = true;
        _cameraMessage = '人脸信息已录入，可用于配送实时核验';
      });
      _show(response.data['message']?.toString() ?? '人脸信息已录入');
    } on DioException catch (error) {
      _show(error.response?.data?['error']?.toString() ?? '录入失败');
    } on CameraException catch (error) {
      _show(error.description ?? '摄像头拍摄失败');
    } finally {
      if (mounted) {
        setState(() => _saving = false);
      }
    }
  }

  void _show(String message) {
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    final ready = controller?.value.isInitialized == true;
    return Scaffold(
      appBar: AppBar(title: const Text('身份认证')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        Chip(
                          label: Text(_enrolled ? '已录入人脸' : '未录入人脸'),
                          backgroundColor: (_enrolled
                              ? const Color(0xFFDCFCE7)
                              : const Color(0xFFFEF3C7)),
                        ),
                        const SizedBox(width: 10),
                        const Expanded(
                          child: Text(
                            '采集后直接保存至当前 HIS 账户',
                            style: TextStyle(color: Colors.grey, fontSize: 12),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 14),
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
                                const Center(
                                  child: CircularProgressIndicator(),
                                ),
                              Center(
                                child: Container(
                                  width: 205,
                                  height: 275,
                                  decoration: BoxDecoration(
                                    border: Border.all(
                                      color: Colors.white.withValues(
                                        alpha: .85,
                                      ),
                                      width: 2,
                                    ),
                                    borderRadius: BorderRadius.circular(110),
                                  ),
                                ),
                              ),
                              Positioned(
                                left: 16,
                                right: 16,
                                bottom: 16,
                                child: DecoratedBox(
                                  decoration: BoxDecoration(
                                    color: Colors.black.withValues(alpha: .5),
                                    borderRadius: BorderRadius.circular(14),
                                  ),
                                  child: Padding(
                                    padding: const EdgeInsets.all(12),
                                    child: Text(
                                      _cameraMessage,
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
                      '非镜像预览。正对镜头、保持光线充足后，点击下方按钮直接录入人脸数据。',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey, fontSize: 12),
                    ),
                    const SizedBox(height: 12),
                    FilledButton.icon(
                      onPressed: _saving || _cameraLoading || !ready
                          ? null
                          : _captureAndSave,
                      icon: const Icon(Icons.face_retouching_natural),
                      label: Text(
                        _saving ? '正在录入…' : (_enrolled ? '重新采集并更新' : '采集并录入人脸'),
                      ),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}
