# 智慧医疗移动端系统 (Hospital Mobile)

本项目是一款基于 Flutter 开发的智慧医疗移动端应用，旨在为医院提供便捷的药品追溯、处方管理及移动办公解决方案。

## 🚀 项目特性

- **高效扫码**：集成 `mobile_scanner`，针对药品追溯码/二维码进行了 UI 优化，支持动态扫描线动画。
- **状态管理**：采用 `Provider` 进行全局状态管理，保证数据流清晰。
- **网络请求**：基于 `Dio` 封装的高效网络层，支持拦截器与异常处理。
- **安全存储**：使用 `flutter_secure_storage` 对用户信息和敏感令牌进行加密存储。
- **工程化目录**：清晰的业务逻辑层（Data/Core/Views/Providers）划分。

## 🛠️ 技术栈

- **框架**: [Flutter 3.x](https://flutter.dev/)
- **语言**: [Dart](https://dart.dev/)
- **网络**: [Dio](https://pub.dev/packages/dio)
- **状态管理**: [Provider](https://pub.dev/packages/provider)
- **扫码**: [Mobile Scanner](https://pub.dev/packages/mobile_scanner)

## 📂 项目结构

```text
lib/
├── core/          # 核心工具类、常量定义
├── data/          # 数据模型 (Models) 与 API 接口
├── providers/     # 状态管理业务逻辑
├── views/         # UI 界面 (包括优化后的 ScannerPage)
└── main.dart      # 程序入口
```

## 📦 快速开始

### 环境准备
- Flutter SDK (建议版本 3.10.0+)
- Android Studio / VS Code

### 运行步骤
1. 克隆项目到本地：
   ```bash
   git clone https://github.com/your-username/hospital_mobile.git
   ```
2. 安装依赖：
   ```bash
   flutter pub get
   ```
3. 运行项目：
   ```bash
   flutter run
   ```

## 🎨 UI 预览
- **扫码页**：经过定制化的蓝色发光扫描框，提供流畅的视觉交互体验。

---

## 📄 开源协议
[MIT License](LICENSE)
