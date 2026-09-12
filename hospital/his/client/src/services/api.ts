import axios from 'axios';
import type {
  LoginResponse,
  Patient,
  PatientFormData,
  Medicine,
  MedicineFormData,
  Prescription,
  PrescriptionFormData,
  MedicineLocation,
  MedicineLocationFormData,
  MedicineTraceCode,
  MedicineTraceCodeFormData,
  PaginatedResponse,
} from '../types';

export interface AuditChainRecord {
  id: number;
  event_type: string;
  entity_type: string;
  entity_id: string;
  trace_code_hash: string | null;
  prescription_hash: string | null;
  operator_hash: string | null;
  flow_status: string;
  event_time: string;
  payload_hash: string;
  previous_hash: string;
  current_hash: string;
  snapshot_hash?: string | null;
  change_id?: number | null;
  created_at: string;
}

export interface AuditBranchRecord {
  kind: 'change' | 'completion' | 'continuation';
  source_record_id: number | null;
  event_type: string;
  entity_id: string;
  event_time: string;
  payload_hash: string;
  previous_hash: string;
  current_hash: string;
}

export interface AuditChainVerifyResult {
  valid: boolean;
  total: number;
  last_hash?: string;
  broken_at?: number;
  expected_previous_hash?: string;
  actual_previous_hash?: string;
}

export interface AuditChainChange {
  id: number;
  change_type?: 'updated' | 'deleted';
  prescription_id: number;
  prescription_code: string | null;
  changes: Array<{ field: string; before: unknown; after: unknown }>;
  old_snapshot_hash: string;
  new_snapshot_hash: string;
  actor_name: string | null;
  actor_source: string;
  ai_analysis: string | null;
  ai_status: 'pending' | 'running' | 'completed' | 'rules_fallback' | 'failed';
  status: 'pending' | 'accepted' | 'superseded';
  detected_at: string;
  accepted_at: string | null;
  baseline_record_id?: number | null;
  base_continuation_records?: AuditChainRecord[];
  branch_records?: AuditBranchRecord[];
}

export interface PrescriptionAnalysisResult {
  summary: string;
  risk_level: '低' | '中' | '高' | '需复核';
  findings: string[];
  suggestions: string[];
  model: string;
  analyzed_at: string;
  simulated: boolean;
}
const apiBaseURL = import.meta.env.VITE_API_BASE_URL;
const apiTimeout = Number(import.meta.env.VITE_API_TIMEOUT_MS);
const api = axios.create({
  baseURL: apiBaseURL,
  timeout: apiTimeout,
});
const refreshApi = axios.create({ baseURL: apiBaseURL, timeout: apiTimeout });
let refreshPromise: Promise<LoginResponse> | null = null;

const clearStoredSession = () => {
  localStorage.removeItem('token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
};

// Auto-attach token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const originalRequest = err.config as (typeof err.config & { _retry?: boolean }) | undefined;
    const isAuthRequest = String(originalRequest?.url || '').includes('/auth/');
    const refreshToken = localStorage.getItem('refresh_token');

    if (err.response?.status === 401 && originalRequest && !originalRequest._retry && !isAuthRequest && refreshToken) {
      originalRequest._retry = true;
      try {
        if (!refreshPromise) {
          refreshPromise = refreshApi
            .post<LoginResponse>('/auth/refresh', { refresh_token: refreshToken })
            .then((response) => response.data)
            .finally(() => { refreshPromise = null; });
        }
        const session = await refreshPromise;
        localStorage.setItem('token', session.token);
        localStorage.setItem('refresh_token', session.refresh_token);
        localStorage.setItem('user', JSON.stringify(session.user));
        originalRequest.headers.Authorization = `Bearer ${session.token}`;
        return api.request(originalRequest);
      } catch {
        clearStoredSession();
        if (window.location.pathname !== '/login') window.location.replace('/login');
      }
    } else if (err.response?.status === 401 && !isAuthRequest) {
      clearStoredSession();
      if (window.location.pathname !== '/login') window.location.replace('/login');
    }
    return Promise.reject(err);
  }
);

// Auth
export const authApi = {
  login: (username: string, password: string) =>
    api.post<LoginResponse>('/auth/login', { username, password }).then((r) => r.data),

  me: () => api.get('/auth/me').then((r) => r.data),
};

// Patients
export const patientApi = {
  list: (params?: { page?: number; pageSize?: number; keyword?: string }) =>
    api
      .get<PaginatedResponse<Patient>>('/patients', { params })
      .then((r) => r.data),

  getById: (id: number) =>
    api.get<Patient>(`/patients/${id}`).then((r) => r.data),

  create: (data: PatientFormData) =>
    api.post('/patients', data).then((r) => r.data),

  update: (id: number, data: PatientFormData) =>
    api.put(`/patients/${id}`, data).then((r) => r.data),

  delete: (id: number) =>
    api.delete(`/patients/${id}`).then((r) => r.data),
};

// Medicines
export const medicineApi = {
  list: (params?: { page?: number; pageSize?: number; keyword?: string }) =>
    api
      .get<PaginatedResponse<Medicine>>('/medicines', { params })
      .then((r) => r.data),

  create: (data: MedicineFormData) =>
    api.post('/medicines', data).then((r) => r.data),

  update: (id: number, data: MedicineFormData) =>
    api.put(`/medicines/${id}`, data).then((r) => r.data),

  delete: (id: number) =>
    api.delete(`/medicines/${id}`).then((r) => r.data),

  setPrefix: (id: number, prefix: string) =>
    api.put(`/medicines/${id}/prefix`, { prefix }).then((r) => r.data),

  deletePrefix: (id: number) =>
    api.delete(`/medicines/${id}/prefix`).then((r) => r.data),
};

// Medicine Locations
export const medicineLocationApi = {
  list: (params?: { page?: number; pageSize?: number; keyword?: string }) =>
    api
      .get<PaginatedResponse<MedicineLocation>>('/medicine-locations', { params })
      .then((r) => r.data),

  getById: (id: number) =>
    api.get<MedicineLocation>(`/medicine-locations/${id}`).then((r) => r.data),

  create: (data: MedicineLocationFormData) =>
    api.post('/medicine-locations', data).then((r) => r.data),

  update: (id: number, data: MedicineLocationFormData) =>
    api.put(`/medicine-locations/${id}`, data).then((r) => r.data),

  delete: (id: number) =>
    api.delete(`/medicine-locations/${id}`).then((r) => r.data),
};

// Medicine Trace Codes
export const medicineTraceCodeApi = {
  list: (params?: { page?: number; pageSize?: number; medicine_id?: number }) =>
    api
      .get<PaginatedResponse<MedicineTraceCode>>('/medicine-trace-codes', { params })
      .then((r) => r.data),

  create: (data: MedicineTraceCodeFormData | MedicineTraceCodeFormData[]) =>
    api.post('/medicine-trace-codes', data).then((r) => r.data),

  update: (id: number, data: MedicineTraceCodeFormData) =>
    api.put(`/medicine-trace-codes/${id}`, data).then((r) => r.data),

  delete: (id: number) =>
    api.delete(`/medicine-trace-codes/${id}`).then((r) => r.data),

  scan: (id: number) =>
    api.put<MedicineTraceCode>(`/medicine-trace-codes/${id}/scan`).then((r) => r.data),

  unscan: (id: number) =>
    api.put<MedicineTraceCode>(`/medicine-trace-codes/${id}/unscan`).then((r) => r.data),

  scanByCode: (trace_code: string) =>
    api.post('/medicine-trace-codes/scan-by-code', { trace_code }).then((r) => r.data),

  lookup: (trace_code: string) =>
    api.get('/medicine-trace-codes/lookup', { params: { trace_code } }).then((r) => r.data),

  registerByPrefix: (trace_code: string) =>
    api.post('/medicine-trace-codes/register-by-prefix', { trace_code }).then((r) => r.data),

  generateAll: () =>
    api.post('/medicine-trace-codes/generate-all').then((r) => r.data),

  regenerateAll: () =>
    api.post('/medicine-trace-codes/regenerate-all').then((r) => r.data),
};

// Audit chain
export const auditChainApi = {
  list: (params?: { page?: number; pageSize?: number }) =>
    api
      .get<PaginatedResponse<AuditChainRecord>>('/audit-chain', { params })
      .then((r) => r.data),

  verify: () =>
    api.get<AuditChainVerifyResult>('/audit-chain/verify').then((r) => r.data),

  inspect: () =>
    api.post<{ changes: AuditChainChange[]; created: number }>('/audit-chain/inspect').then((r) => r.data),

  analyze: (id: number) =>
    api.post<AuditChainChange>(`/audit-chain/changes/${id}/analyze`).then((r) => r.data),

  accept: (id: number) =>
    api.post(`/audit-chain/changes/${id}/accept`).then((r) => r.data),

  reject: (id: number) =>
    api.post(`/audit-chain/changes/${id}/reject`).then((r) => r.data),

  demoTamper: () =>
    api.post('/audit-chain/demo/tamper').then((r) => r.data),

  clear: () =>
    api.delete('/audit-chain').then((r) => r.data),
};
// Prescriptions
export const prescriptionApi = {
  list: (params?: { page?: number; pageSize?: number; status?: string }) =>
    api
      .get<PaginatedResponse<Prescription>>('/prescriptions', { params })
      .then((r) => r.data),

  getById: (id: number) =>
    api.get<Prescription>(`/prescriptions/${id}`).then((r) => r.data),

  analyze: (id: number) =>
    api.post<PrescriptionAnalysisResult>(`/prescriptions/${id}/analyze`).then((r) => r.data),

  create: (data: PrescriptionFormData) =>
    api.post('/prescriptions', data).then((r) => r.data),

  dispense: (id: number) =>
    api.put(`/prescriptions/${id}/dispense`).then((r) => r.data),

  resetTest: (id: number) =>
    api.post(`/prescriptions/${id}/reset-test`).then((r) => r.data),

  delete: (id: number) =>
    api.delete(`/prescriptions/${id}`).then((r) => r.data),

  deleteAll: () =>
    api.delete('/prescriptions/all').then((r) => r.data),
};

export default api;
