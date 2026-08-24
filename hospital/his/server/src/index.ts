import express from 'express';
import cors from 'cors';
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
const app = express();
const PORT = Number(process.env.PORT || 3001);
const HOST = process.env.HOST || '0.0.0.0';

// Middleware
app.use(cors());
app.use(express.json({ limit: '6mb' }));

// Health check
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
});
