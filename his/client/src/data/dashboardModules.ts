export type DashboardModuleKey =
  | 'dispense'
  | 'medicineInfo'
  | 'reports'
  | 'patients'
  | 'medicineLocations'
  | 'medicineSettings'
  | 'writeoff'
  | 'operationLog'
  | 'medicineDown'
  | 'restock'
  | 'inventory'
  | 'prescriptions'
  | 'deliveryRecords'
  | 'faceAuth'
  | 'robots'
  | 'dispenseManagement';

export interface DashboardModule {
  key: DashboardModuleKey;
  to: string | null;
  label: string;
  available: boolean;
}

export const DASHBOARD_MODULES: DashboardModule[] = [
  { key: 'dispense', to: '/dispense', label: '医嘱取药', available: true },
  { key: 'medicineInfo', to: '/medicine-info', label: '药盒信息', available: true },
  { key: 'reports', to: '/reports', label: '报表生成', available: true },
  { key: 'patients', to: '/patients', label: '病人管理', available: true },
  { key: 'medicineLocations', to: '/medicine-locations', label: '药品管理', available: true },
  { key: 'medicineSettings', to: '/medicine-settings', label: '药盒设置', available: true },
  { key: 'writeoff', to: '/writeoff', label: '销账', available: true },
  { key: 'operationLog', to: '/operation-log', label: '可信审计链', available: true },
  { key: 'medicineDown', to: '/medicine-down', label: '药品下架', available: true },
  { key: 'restock', to: '/restock', label: '补药', available: true },
  { key: 'inventory', to: '/inventory', label: '库存查询', available: true },
  { key: 'prescriptions', to: '/prescriptions', label: '处方记录', available: true },
  { key: 'deliveryRecords', to: '/delivery-records', label: '配送记录', available: true },
  { key: 'faceAuth', to: '/face-auth', label: '人脸认证', available: true },
  { key: 'robots', to: '/robots', label: '机器人管理', available: true },
  { key: 'dispenseManagement', to: '/dispense-management', label: '配药管理', available: true },
];
