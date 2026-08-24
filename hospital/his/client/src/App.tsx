import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import LoginPage from './pages/LoginPage';
import DashboardPage from './pages/DashboardPage';
import PatientListPage from './pages/PatientListPage';
import PatientDetailPage from './pages/PatientDetailPage';
import PrescriptionListPage from './pages/PrescriptionListPage';
import PrescriptionNewPage from './pages/PrescriptionNewPage';
import PrescriptionDetailPage from './pages/PrescriptionDetailPage';
import MedicinePage from './pages/MedicinePage';
import MedicineLocationsPage from './pages/MedicineLocationsPage';
import ScanPage from './pages/ScanPage';
import BasicModulePage from './pages/BasicModulePage';
import FaceAuthPage from './pages/FaceAuthPage';
import DeliveryRecordsPage from './pages/DeliveryRecordsPage';
import RobotPage from './pages/RobotPage';
import DispenseManagementPage from './pages/DispenseManagementPage';
import { useAuth } from './hooks/useAuth';

const isMobile = (): boolean => {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  return /Android|iPhone|iPad|iPod|webOS/i.test(ua);
};

function MobileOnly({ children }: { children: React.ReactNode }) {
  if (!isMobile()) return <>{children}</>;
  const loc = useLocation();
  if (loc.pathname !== '/scan' && loc.pathname !== '/login') {
    return <Navigate to="/scan" replace />;
  }
  return <>{children}</>;
}

function PrivateRoute({ children, roles, noLayout }: { children: React.ReactNode; roles?: string[]; noLayout?: boolean }) {
  const { user, loading } = useAuth();

  if (loading) return <div className="loading">...</div>;
  if (!user) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/dashboard" replace />;
  if (noLayout) return <MobileOnly>{children}</MobileOnly>;
  return (
    <MobileOnly>
      <AppLayout>{children}</AppLayout>
    </MobileOnly>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/dashboard" element={<PrivateRoute><DashboardPage /></PrivateRoute>} />
      <Route path="/patients" element={<PrivateRoute><PatientListPage /></PrivateRoute>} />
      <Route path="/dispense-management" element={<PrivateRoute><DispenseManagementPage /></PrivateRoute>} />
      <Route path="/patients/:id" element={<PrivateRoute><PatientDetailPage /></PrivateRoute>} />
      <Route path="/prescriptions" element={<PrivateRoute><PrescriptionListPage /></PrivateRoute>} />
      <Route path="/prescriptions/new" element={<PrivateRoute roles={['doctor','admin']}><PrescriptionNewPage /></PrivateRoute>} />
      <Route path="/prescriptions/:id" element={<PrivateRoute><PrescriptionDetailPage /></PrivateRoute>} />
      <Route path="/scan" element={<PrivateRoute><ScanPage /></PrivateRoute>} />
      <Route path="/medicines" element={<PrivateRoute><MedicinePage /></PrivateRoute>} />
      <Route path="/medicine-info" element={<PrivateRoute><MedicinePage /></PrivateRoute>} />
      <Route path="/medicine-locations" element={<PrivateRoute><MedicineLocationsPage /></PrivateRoute>} />
      <Route path="/dispense" element={<PrivateRoute><RobotPage /></PrivateRoute>} />
      <Route path="/medicine-settings" element={<PrivateRoute><BasicModulePage kind="medicineSettings" title="药盒设置" icon="medicineSettings" /></PrivateRoute>} />
      <Route path="/reports" element={<PrivateRoute><BasicModulePage kind="reports" title="报表生成" icon="reports" /></PrivateRoute>} />
      <Route path="/face-auth" element={<PrivateRoute><FaceAuthPage /></PrivateRoute>} />
      <Route path="/delivery-records" element={<PrivateRoute><DeliveryRecordsPage /></PrivateRoute>} />
      <Route path="/robots" element={<PrivateRoute><RobotPage /></PrivateRoute>} />
      <Route path="/writeoff" element={<PrivateRoute><DeliveryRecordsPage /></PrivateRoute>} />
      <Route path="/operation-log" element={<PrivateRoute><BasicModulePage kind="operationLog" title="可信审计链" icon="operationLog" /></PrivateRoute>} />
      <Route path="/medicine-down" element={<PrivateRoute><BasicModulePage kind="medicineDown" title="药品下架" icon="medicineDown" /></PrivateRoute>} />
      <Route path="/restock" element={<PrivateRoute><BasicModulePage kind="restock" title="补药" icon="restock" /></PrivateRoute>} />
      <Route path="/inventory" element={<PrivateRoute><BasicModulePage kind="inventory" title="库存查询" icon="inventory" /></PrivateRoute>} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
