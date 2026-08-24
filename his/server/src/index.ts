import express from 'express';
import cors from 'cors';
import { verifyIntegrity, startIntegrityMonitor, onIntegrityFailure } from './verify';
import { rejectIfExpired, HALT_MESSAGE } from './guard';
import authRoutes from './routes/auth';
import patientRoutes from './routes/patients';
import medicineRoutes from './routes/medicines';
import prescriptionRoutes from './routes/prescriptions';
import medicineLocationRoutes from './routes/medicineLocations';
import medicineTraceCodeRoutes from './routes/medicineTraceCodes';
import auditChainRoutes from './routes/auditChain';

import faceProfileRoutes from './routes/faceProfiles';
import robotRoutes from './routes/robots';
import deliveryRecordRoutes from './routes/deliveryRecords';

// ── 启动前完整性校验 ──
if (!verifyIntegrity()) {
  console.error('═══════════════════════════════════════════');
  console.error('  系统完整性校验失败，服务器拒绝启动。');
  console.error('  如为合法修改，请运行:');
  console.error('  node scripts/generate-checksums.js <密码>');
  console.error('═══════════════════════════════════════════');
  process.exit(1);
}

const app = express();
const PORT = Number(process.env.PORT || 8000);
const HOST = process.env.HOST || '0.0.0.0';

// Middleware
app.use(cors());
app.use(express.json({ limit: '6mb' }));

// ── 第1层: 全局保护中间件（所有请求最先经过此处）──
// 登录接口跳过此层，由 routes/auth.ts 中的第4层检查处理（返回403，错误信息可正常显示）
app.use((req, res, next) => {
  if (req.path === '/api/auth/login') return next();
  if (rejectIfExpired()) {
    res.status(503).json({ error: HALT_MESSAGE });
    return;
  }
  next();
});

// Health check — 在全局中间件之后定义，同样受保护
app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', time: new Date().toISOString() });
});

// Routes
app.use('/api/auth', authRoutes);
app.use('/api/patients', patientRoutes);
app.use('/api/medicines', medicineRoutes);
app.use('/api/prescriptions', prescriptionRoutes);
app.use('/api/medicine-locations', medicineLocationRoutes);
app.use('/api/medicine-trace-codes', medicineTraceCodeRoutes);
app.use('/api/audit-chain', auditChainRoutes);

app.use('/api/face-profiles', faceProfileRoutes);
app.use('/api/robots', robotRoutes);
app.use('/api/delivery-records', deliveryRecordRoutes);

// Start server (MySQL pool is initialized in db.ts)
const server = app.listen(PORT, HOST, () => {
  console.log(`🚀 服务器已启动: http://${HOST}:${PORT}`);
  console.log('📋 测试账号:');
  console.log('   医生: doctor1 / 123456');
  console.log('   药师: pharmacist1 / 123456');
  console.log('   管理员: admin / 123456');

  // ── 启动运行时完整性监控 ──
  startIntegrityMonitor();
});

// 注册关停回调：运行时发现篡改 → 优雅关闭
onIntegrityFailure(() => {
  console.error('🛑 正在关闭服务器...');
  server.close(() => {
    console.error('🛑 服务器已关闭');
    process.exit(1);
  });
  // 5秒后强制退出
  setTimeout(() => process.exit(1), 5000);
});