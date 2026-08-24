// User types
export interface User {
  id: number;
  username: string;
  real_name: string;
  role: 'doctor' | 'pharmacist' | 'admin';
}

export interface LoginResponse {
  token: string;
  user: User;
}

// Patient types
export interface Patient {
  id: number;
  name: string;
  gender: string;
  age: number;
  phone: string;
  id_card: string;
  address: string;
  created_at: string;
  updated_at: string;
  prescriptions?: Prescription[];
}

export interface PatientFormData {
  name: string;
  gender: string;
  age: number | '';
  phone: string;
  id_card: string;
  address: string;
}

// Medicine types
export interface Medicine {
  id: number;
  name: string;
  generic_name: string;
  specification: string;
  drug_form: string;
  manufacturer: string;
  unit: string;
  price: number;
  stock: number;
  category: '处方药' | '非处方药';
  is_narcotic: number;
  image_url: string;
  trace_code_prefix?: string;
  created_at: string;
}

export interface MedicineFormData {
  name: string;
  generic_name: string;
  specification: string;
  drug_form: string;
  manufacturer: string;
  unit: string;
  price: number | '';
  stock: number | '';
  category: string;
  is_narcotic: boolean;
  image_url: string;
  trace_code_prefix: string;
}

// Prescription types
export interface PrescriptionItem {
  id: number;
  prescription_id: number;
  medicine_id: number;
  drug_form: string;
  dosage: string;
  usage_method: string;
  frequency: string;
  days: number;
  quantity: number;
  note: string;
  medicine_name?: string;
  specification?: string;
  manufacturer?: string;
  unit?: string;
  price?: number;
  trace_code?: string;
  trace_status?: 'pending' | 'scanned_identify' | 'scanned_outbound' | 'scanned_confirm';
  scan1_time?: string | null;
  scan2_time?: string | null;
  scan3_time?: string | null;
}

export interface PrescriptionItemFormData {
  medicine_id: number;
  trace_code: string;
  drug_form?: string;
  dosage: string;
  usage_method: string;
  frequency: string;
  days: number;
  quantity: number;
  note: string;
}

export interface Prescription {
  id: number;
  patient_id: number;
  doctor_id: number;
  prescription_code?: string;
  prescription_type: string;
  payment_type: string;
  medical_record_no: string;
  department: string;
  bed_no: string;
  diagnosis: string;
  status: 'pending' | 'approved' | 'rejected' | 'dispensed';
  pharmacist_review_id: number;
  pharmacist_dispense_id: number;
  pharmacist_check_id: number;
  total_amount: number;
  note: string;
  reviewed_at: string;
  dispensed_at: string;
  created_at: string;
  updated_at: string;
  patient_name?: string;
  patient_gender?: string;
  patient_age?: number;
  doctor_name?: string;
  reviewer_name?: string;
  dispenser_name?: string;
  items?: PrescriptionItem[];
}

export interface PrescriptionFormData {
  patient_id: number;
  prescription_type: string;
  payment_type: string;
  medical_record_no: string;
  department: string;
  bed_no: string;
  diagnosis: string;
  note: string;
  items: PrescriptionItemFormData[];
}

// Medicine location types
export interface MedicineLocation {
  id: number;
  medicine_id: number;
  medicine_name: string;
  x: number;
  y: number;
  z: number;
  specification?: string;
  manufacturer?: string;
  trace_code_prefix?: string;
  created_at: string;
}

export interface MedicineLocationFormData {
  medicine_id: number;
  medicine_name: string;
  x: number | '';
  y: number | '';
  z: number | '';
}

// Medicine trace code types
export interface MedicineTraceCode {
  id: number;
  medicine_id: number;
  prescription_id: number | null;
  trace_code: string;
  status: 'pending' | 'scanned_identify' | 'scanned_outbound' | 'scanned_confirm';
  scan1_time: string | null;
  scan2_time: string | null;
  scan3_time: string | null;
  scan1_user_id: number | null;
  scan2_user_id: number | null;
  scan3_user_id: number | null;
  scan1_user_name?: string;
  scan2_user_name?: string;
  scan3_user_name?: string;
  created_at: string;
  updated_at: string;
}

export interface MedicineTraceCodeFormData {
  medicine_id: number;
  trace_code: string;
}

// Paginated response
export interface PaginatedResponse<T> {
  total: number;
  page: number;
  pageSize: number;
  list: T[];
}

// API response wrapper
export interface ApiResponse<T = any> {
  message?: string;
  error?: string;
  [key: string]: any;
}

// Status labels
export const STATUS_LABELS: Record<string, string> = {
  pending: '待审核',
  approved: '已通过',
  rejected: '已驳回',
  dispensed: '已发药',
};

export const STATUS_COLORS: Record<string, string> = {
  pending: '#f0ad4e',
  approved: '#5cb85c',
  rejected: '#d9534f',
  dispensed: '#4a90d9',
};

export const PRESCRIPTION_TYPE_LABELS: Record<string, string> = {
  '普通': '普通处方',
  '急诊': '急诊处方',
  '儿科': '儿科处方',
  '麻醉精一': '麻、精一处方',
  '精二': '精二处方',
};

export const PRESCRIPTION_TYPE_COLORS: Record<string, string> = {
  '普通': '#FFFFFF',
  '急诊': '#FFFDE7',
  '儿科': '#E8F5E9',
  '麻醉精一': '#FFEBEE',
  '精二': '#F5F5F5',
};

export const TRACE_STATUS_LABELS: Record<string, string> = {
  pending: '待扫描',
  scanned_identify: '已识别',
  scanned_outbound: '已出库',
  scanned_confirm: '已完成',
};

export const TRACE_STATUS_COLORS: Record<string, string> = {
  pending: '#f0ad4e',
  scanned_identify: '#4a90d9',
  scanned_outbound: '#5cb85c',
  scanned_confirm: '#8e44ad',
};

export const PAYMENT_LABELS: Record<string, string> = {
  '公费': '公费医疗',
  '医保': '医疗保险',
  '部分自费': '部分自费',
  '自费': '自费',
};
