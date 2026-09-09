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
  | 'prescriptionAnalysis'
  | 'inventory'
  | 'prescriptions';

export interface DashboardModule {
  key: DashboardModuleKey;
  to: string | null;
  label: string;
  available: boolean;
}

export const DASHBOARD_MODULES: DashboardModule[] = [
  { key: 'dispense', to: '/dispense', label: '机器人管理', available: true },
  { key: 'medicineInfo', to: '/medicine-info', label: '药盒信息', available: true },
  { key: 'reports', to: '/reports', label: '报表生成', available: true },
  { key: 'patients', to: '/patients', label: '病人管理', available: true },
  { key: 'medicineLocations', to: '/medicine-locations', label: '药品管理', available: true },
  { key: 'medicineSettings', to: '/medicine-settings', label: '药盒设置', available: true },
  { key: 'writeoff', to: '/writeoff', label: '配送记录', available: true },
  { key: 'operationLog', to: '/operation-log', label: '可信审计链', available: true },
  { key: 'medicineDown', to: '/medicine-down', label: '药品下架', available: true },
  { key: 'prescriptionAnalysis', to: '/prescription-analysis', label: '处方智析', available: true },
  { key: 'inventory', to: '/inventory', label: '库存查询', available: true },
  { key: 'prescriptions', to: '/prescriptions', label: '处方记录', available: true },
];
