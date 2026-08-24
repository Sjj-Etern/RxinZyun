import { useState, useEffect, useMemo, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { prescriptionApi, patientApi, medicineApi, medicineTraceCodeApi } from '../services/api';
import type { Patient, Medicine, PrescriptionItemFormData } from '../types';
import Modal from '../components/Modal';
import { showToast } from '../components/Toast';
import ModuleIcon from '../components/ModuleIcon';
import GlassSelect from '../components/GlassSelect';

interface MedItem extends PrescriptionItemFormData {
  medicine_name?: string; specification?: string; unit?: string; price?: number;
}

type PrescriptionDraft = {
  prescriptionType?: string;
  paymentType?: string;
  medicalRecordNo?: string;
  department?: string;
  bedNo?: string;
  selectedPatient?: Patient | null;
  diagnosis?: string;
  note?: string;
  items?: MedItem[];
};

const DRAFT_KEY = 'prescription_new_draft';

const loadDraft = (): PrescriptionDraft | null => {
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_e) {
    return null;
  }
};

const fadeUp = { initial: { opacity: 0, y: 20 }, animate: { opacity: 1, y: 0 } };

// 处方类型对应液态玻璃色
const PRESCRIPTION_COLORS: Record<string, { bg: string; border: string; accent: string; label: string }> = {
  '普通': { bg: 'rgba(255,255,255,0.54)', border: 'rgba(49,120,198,0.22)', accent: '#3178C6', label: '普通处方' },
  '急诊': { bg: 'rgba(255,245,226,0.62)', border: 'rgba(245,158,11,0.32)', accent: '#D97706', label: '急诊处方' },
  '儿科': { bg: 'rgba(232,255,249,0.62)', border: 'rgba(50,198,186,0.32)', accent: '#0F9F92', label: '儿科处方' },
  '麻醉精一': { bg: 'rgba(255,239,246,0.64)', border: 'rgba(231,140,168,0.36)', accent: '#C84B74', label: '麻醉、精一处方' },
  '精二': { bg: 'rgba(238,242,255,0.64)', border: 'rgba(99,102,241,0.28)', accent: '#4F46E5', label: '精二处方' },
};

const PRESCRIPTION_TYPE_OPTIONS = [
  { value: '普通', label: '普通处方' },
  { value: '急诊', label: '急诊处方' },
  { value: '儿科', label: '儿科处方' },
  { value: '麻醉精一', label: '麻、精一' },
  { value: '精二', label: '精二处方' },
];

const PAYMENT_TYPE_OPTIONS = [
  { value: '公费', label: '公费医疗' },
  { value: '医保', label: '医疗保险' },
  { value: '部分自费', label: '部分自费' },
  { value: '自费', label: '自费' },
];

const USAGE_METHOD_OPTIONS = [
  { value: '口服', label: '口服' },
  { value: '外用', label: '外用' },
  { value: '注射', label: '注射' },
  { value: '含服', label: '含服' },
  { value: '吸入', label: '吸入' },
];

const FREQUENCY_OPTIONS = [
  { value: '每日1次', label: '每日1次' },
  { value: '每日2次', label: '每日2次' },
  { value: '每日3次', label: '每日3次' },
  { value: '每日4次', label: '每日4次' },
  { value: '睡前1次', label: '睡前1次' },
  { value: '必要时', label: '必要时' },
];

export default function PrescriptionNewPage() {
  const navigate = useNavigate();
  const savedDraft = useMemo(() => loadDraft(), []);

  // 处方前记
  const [prescriptionType, setPrescriptionType] = useState(savedDraft?.prescriptionType || '普通');
  const [paymentType, setPaymentType] = useState(savedDraft?.paymentType || '医保');
  const [medicalRecordNo, setMedicalRecordNo] = useState(savedDraft?.medicalRecordNo || '');
  const [department, setDepartment] = useState(savedDraft?.department || '');
  const [bedNo, setBedNo] = useState(savedDraft?.bedNo || '');

  const [patientSearch, setPatientSearch] = useState('');
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(savedDraft?.selectedPatient || null);
  const [patientSearching, setPatientSearching] = useState(false);

  const [diagnosis, setDiagnosis] = useState(savedDraft?.diagnosis || '');
  const [note, setNote] = useState(savedDraft?.note || '');

  const [medSearch, setMedSearch] = useState('');
  const [medicines, setMedicines] = useState<Medicine[]>([]);
  const [medSearching, setMedSearching] = useState(false);
  const [traceSearching, setTraceSearching] = useState(false);
  const [items, setItems] = useState<MedItem[]>(savedDraft?.items || []);

  const [medModalOpen, setMedModalOpen] = useState(false);
  const [selectedMed, setSelectedMed] = useState<Medicine | null>(null);
  const [medForm, setMedForm] = useState({ dosage: '', trace_code: '', usage_method: '口服', frequency: '每日3次', days: 3, quantity: 1, note: '' });

  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const searchPatients = async (kw: string) => {
    if (!kw.trim()) { setPatients([]); return; }
    setPatientSearching(true);
    try { const data = await patientApi.list({ page: 1, pageSize: 10, keyword: kw }); setPatients(data.list); }
    catch (err) { console.error(err); }
    finally { setPatientSearching(false); }
  };

  const searchMedicines = async (kw: string) => {
    if (!kw.trim()) { setMedicines([]); return; }
    const keyword = kw.trim();
    if (/^\d{20,}$/.test(keyword)) {
      await lookupTraceCodeValue(keyword);
      setMedicines([]);
      return;
    }
    setMedSearching(true);
    try { const data = await medicineApi.list({ page: 1, pageSize: 10, keyword: kw }); setMedicines(data.list); }
    catch (err) { console.error(err); }
    finally { setMedSearching(false); }
  };

  useEffect(() => { const timer = setTimeout(() => searchPatients(patientSearch), 300); return () => clearTimeout(timer); }, [patientSearch]);
  useEffect(() => { const timer = setTimeout(() => searchMedicines(medSearch), 300); return () => clearTimeout(timer); }, [medSearch]);
  useEffect(() => {
    const draft: PrescriptionDraft = {
      prescriptionType,
      paymentType,
      medicalRecordNo,
      department,
      bedNo,
      selectedPatient,
      diagnosis,
      note,
      items,
    };
    localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
  }, [prescriptionType, paymentType, medicalRecordNo, department, bedNo, selectedPatient, diagnosis, note, items]);

  const selectPatient = (p: Patient) => { setSelectedPatient(p); setPatientSearch(''); setPatients([]); };

  const openMedForm = (m: Medicine, traceCode = '') => {
    setSelectedMed(m);
    setMedForm({ dosage: '', trace_code: traceCode, usage_method: '口服', frequency: '每日3次', days: 3, quantity: 1, note: '' });
    setMedModalOpen(true);
  };

  const lookupTraceCodeValue = async (traceCode: string) => {
    if (!traceCode) { setError('请输入追溯码'); return; }
    if (items.length >= 5) { setError('每张处方最多添加5种药品'); return; }
    if (items.some(item => item.trace_code === traceCode)) { setError('追溯码不能重复'); return; }

    setTraceSearching(true);
    setError('');
    try {
      const data = await medicineTraceCodeApi.lookup(traceCode);
      if (data.prescription_id) {
        setError('该追溯码已关联其他处方，不能用于新处方');
        return;
      }
      if (data.status !== 'pending' || data.scan1_time || data.scan2_time || data.scan3_time) {
        setError('该追溯码已被扫描，不能用于新处方');
        return;
      }
      if (items.some(item => item.medicine_id === data.medicine_id)) {
        setError('处方中的药品不能重复');
        return;
      }

      const medicine: Medicine = {
        id: data.medicine_id,
        name: data.medicine_name,
        generic_name: data.generic_name || '',
        specification: data.specification || '',
        drug_form: data.drug_form || '',
        manufacturer: data.manufacturer || '',
        unit: data.unit || '',
        price: Number(data.price || 0),
        stock: Number(data.stock || 0),
        category: (data.category || '处方药') as Medicine['category'],
        is_narcotic: data.is_narcotic || 0,
        image_url: data.image_url || '',
        created_at: data.created_at || '',
      };

      setMedSearch('');
      setMedicines([]);
      openMedForm(medicine, traceCode);
    } catch (err: any) {
      setError(err.response?.data?.error || '追溯码识别失败');
    } finally {
      setTraceSearching(false);
    }
  };

  const lookupTraceCode = async () => {
    await lookupTraceCodeValue(medSearch.trim());
  };

  const addMedItem = () => {
    const traceCode = medForm.trace_code.trim();
    if (items.length >= 5) {
      setError('每张处方最多添加5种药品');
      return;
    }
    if (!selectedMed || !medForm.dosage.trim() || !traceCode) {
      setError('请填写药品用量和追溯码');
      return;
    }
    if (items.some(item => item.medicine_id === selectedMed.id)) {
      setError('处方中的药品不能重复');
      return;
    }
    if (items.some(item => item.trace_code === traceCode)) {
      setError('追溯码不能重复');
      return;
    }
    setError('');
    setItems([...items, {
      medicine_id: selectedMed.id, medicine_name: selectedMed.name,
      specification: selectedMed.specification, unit: selectedMed.unit,
      drug_form: selectedMed.drug_form,
      price: selectedMed.price,
      ...medForm,
      dosage: medForm.dosage.trim(),
      trace_code: traceCode,
    }]);
    setMedModalOpen(false); setSelectedMed(null); setMedSearch(''); setMedicines([]);
  };

  const removeItem = (index: number) => setItems(items.filter((_, i) => i !== index));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault(); setError('');
    if (!selectedPatient) { setError('请先选择病人'); return; }
    if (!diagnosis.trim()) { setError('请填写临床诊断'); return; }
    if (items.length === 0) { setError('请至少添加一种药品'); return; }
    if (items.length > 5) { setError('每张处方最多添加5种药品'); return; }
    if (items.some(item => !item.trace_code?.trim())) { setError('每个药品都必须填写追溯码'); return; }
    setConfirmOpen(true);
  };

  const confirmSubmit = async () => {
    setConfirmOpen(false);
    setSubmitting(true);
    try {
      const res = await prescriptionApi.create({
        patient_id: selectedPatient!.id,
        prescription_type: prescriptionType, payment_type: paymentType,
        medical_record_no: medicalRecordNo, department, bed_no: bedNo,
        diagnosis: diagnosis.trim(), note: note.trim(),
        items: items.map(({ medicine_id, trace_code, drug_form, dosage, usage_method, frequency, days, quantity, note }) =>
          ({ medicine_id, trace_code, drug_form, dosage, usage_method, frequency, days, quantity, note })),
      });
      localStorage.removeItem(DRAFT_KEY);
      showToast(res.message || '处方已提交，等待药师审核', 'success');
      navigate(`/prescriptions/${res.id}`);
    } catch (err: any) { setError(err.response?.data?.error || '提交失败'); }
    finally { setSubmitting(false); }
  };

  return (
    <div className="prescription-new-page">
      <motion.div className="page-header prescription-header" {...fadeUp} transition={{ duration: 0.4 }}>
        <div className="prescription-title-icon">
          <ModuleIcon name="prescriptionNew" size={54} />
        </div>
        <div>
          <h1>开具处方</h1>
          <p>选择病人 → 填写诊断 → 添加药品 → 提交处方</p>
        </div>
      </motion.div>

      {error && <motion.div className="alert alert--error" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}>{error}</motion.div>}

      <form onSubmit={handleSubmit}>
        {/* 处方类型标签 */}
        <motion.div {...fadeUp} transition={{ delay: 0.03 }} style={{ marginBottom: 12, textAlign: 'center' }}>
          <span style={{
            display: 'inline-block', padding: '7px 22px', borderRadius: 50,
            background: PRESCRIPTION_COLORS[prescriptionType].bg,
            border: `2px solid ${PRESCRIPTION_COLORS[prescriptionType].border}`,
            fontWeight: 700, fontSize: 15, color: PRESCRIPTION_COLORS[prescriptionType].accent,
            backdropFilter: 'var(--blur)',
            boxShadow: `0 12px 26px ${PRESCRIPTION_COLORS[prescriptionType].border}`,
          }}>
            {PRESCRIPTION_COLORS[prescriptionType].label}
          </span>
        </motion.div>

        {/* 处方前记 */}
        <motion.div className="glass-card" style={{
          padding: 20, marginBottom: 16,
          background: PRESCRIPTION_COLORS[prescriptionType].bg,
          borderColor: PRESCRIPTION_COLORS[prescriptionType].border,
        }} {...fadeUp} transition={{ delay: 0.05 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12, color: PRESCRIPTION_COLORS[prescriptionType].accent }}>处方前记</h3>
          <div className="form-grid form-grid--3">
            <div className="form-group">
              <label>处方类型</label>
              <GlassSelect value={prescriptionType} options={PRESCRIPTION_TYPE_OPTIONS} onChange={setPrescriptionType} />
            </div>
            <div className="form-group">
              <label>费别</label>
              <GlassSelect value={paymentType} options={PAYMENT_TYPE_OPTIONS} onChange={setPaymentType} />
            </div>
            <div className="form-group">
              <label>病历号</label>
              <input className="glass-input" value={medicalRecordNo} onChange={(e) => setMedicalRecordNo(e.target.value)} placeholder="门诊/住院病历号" />
            </div>
            <div className="form-group">
              <label>科别</label>
              <input className="glass-input" value={department} onChange={(e) => setDepartment(e.target.value)} placeholder="如：内科、儿科" />
            </div>
            <div className="form-group">
              <label>床位号</label>
              <input className="glass-input" value={bedNo} onChange={(e) => setBedNo(e.target.value)} placeholder="如：12床" />
            </div>
          </div>
        </motion.div>

        {/* 病人选择 + 诊断 */}
        <motion.div className="glass-card" style={{
          padding: 20, marginBottom: 16,
          background: PRESCRIPTION_COLORS[prescriptionType].bg,
          borderColor: PRESCRIPTION_COLORS[prescriptionType].border,
        }} {...fadeUp} transition={{ delay: 0.08 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>① 选择病人与诊断</h3>
          {selectedPatient ? (
            <div className="flex-between" style={{ padding: '12px 16px', background: 'rgba(92,184,92,0.08)', borderRadius: 12 }}>
              <div>
                <strong>{selectedPatient.name}</strong>
                <span style={{ marginLeft: 12, color: 'var(--text-secondary)', fontSize: 14 }}>{selectedPatient.gender} · {selectedPatient.age}岁 · {selectedPatient.phone || '无手机号'}</span>
              </div>
              <button type="button" className="glass-btn glass-btn--outline glass-btn--sm" onClick={() => setSelectedPatient(null)}>更换病人</button>
            </div>
          ) : (
            <div>
              <div style={{ display: 'flex', gap: 8 }}>
                <input className="glass-input" style={{ flex: 1 }} placeholder="搜索病人姓名或手机号..." value={patientSearch} onChange={(e) => setPatientSearch(e.target.value)} />
              </div>
              {patientSearching && <div style={{ padding: 12, color: 'var(--text-muted)', fontSize: 14 }}>搜索中...</div>}
              {patients.length > 0 && (
                <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 8 }}>
                  {patients.map((p) => (
                    <motion.div key={p.id} className="glass-card" style={{ padding: '14px 18px', cursor: 'pointer' }}
                      onClick={() => selectPatient(p)} whileHover={{ scale: 1.02 }}>
                      <strong style={{ fontSize: 16 }}>{p.name}</strong>
                      <span style={{ marginLeft: 12, color: 'var(--text-secondary)', fontSize: 13 }}>{p.gender} · {p.age}岁 · {p.phone || '无手机号'} · #{p.id}</span>
                    </motion.div>
                  ))}
                </div>
              )}
            </div>
          )}
          <div className="form-group mt-md">
            <label>临床诊断 *</label>
            <input className="glass-input" placeholder="请输入诊断结果，如：上呼吸道感染" value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} />
          </div>
          <div className="form-group mt-md">
            <label>备注</label>
            <textarea className="glass-input" placeholder="处方备注（可选）" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
          </div>
        </motion.div>

        {/* 处方正文 */}
        <motion.div className="glass-card" style={{
          padding: 20, marginBottom: 16,
          background: PRESCRIPTION_COLORS[prescriptionType].bg,
          borderColor: PRESCRIPTION_COLORS[prescriptionType].border,
        }} {...fadeUp} transition={{ delay: 0.15 }}>
          <div className="flex-between" style={{ marginBottom: 12 }}>
            <h3 style={{ fontSize: 16, fontWeight: 600, color: PRESCRIPTION_COLORS[prescriptionType].accent }}>处方正文 (Rp) — 已添加 {items.length}/5 种药品</h3>
            {items.length >= 5 && <span style={{ color: '#d9534f', fontSize: 13, fontWeight: 600 }}>已达上限</span>}
          </div>

          {items.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <table className="glass-table">
                <thead>
                  <tr><th>药品名称</th><th>追溯码</th><th>规格</th><th>用量</th><th>用法</th><th>频次</th><th>天数</th><th>数量</th><th>操作</th></tr>
                </thead>
                <tbody>
                  <AnimatePresence>
                    {items.map((item, i) => (
                      <motion.tr key={i} initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }}>
                        <td><strong>{item.medicine_name}</strong></td>
                        <td><code style={{ fontSize: 11, wordBreak: 'break-all' }}>{item.trace_code}</code></td>
                        <td style={{ fontSize: 13 }}>{item.specification}</td>
                        <td>{item.dosage}</td>
                        <td>{item.usage_method}</td>
                        <td>{item.frequency}</td>
                        <td>{item.days}天</td>
                        <td>{item.quantity}{item.unit}</td>
                        <td>
                          <button type="button" className="glass-btn glass-btn--danger glass-btn--sm" onClick={() => removeItem(i)}>删除</button>
                        </td>
                      </motion.tr>
                    ))}
                  </AnimatePresence>
                </tbody>
              </table>
            </div>
          )}

          {items.length < 5 && (
            <>
              <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                <input
                  className="glass-input"
                  style={{ flex: 1 }}
                  placeholder="搜索药品名称或输入追溯码..."
                  value={medSearch}
                  onChange={(e) => setMedSearch(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); lookupTraceCode(); } }}
                />
                <button type="button" className="glass-btn glass-btn--primary" onClick={lookupTraceCode} disabled={traceSearching}>
                  {traceSearching ? '识别中...' : '识别'}
                </button>
              </div>
              {medSearching && <div style={{ padding: 8, color: 'var(--text-muted)', fontSize: 14 }}>搜索中...</div>}
              {medicines.length > 0 && (
                <div style={{ marginTop: 8, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 8 }}>
                  {medicines.map((m) => (
                    <motion.div key={m.id} className="glass-card"
                      style={{ padding: '14px 18px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                      onClick={() => openMedForm(m)} whileHover={{ scale: 1.02 }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <strong style={{ fontSize: 16 }}>{m.name}</strong>
                        {m.generic_name && <span style={{ marginLeft: 6, color: 'var(--blue)', fontSize: 12 }}>({m.generic_name})</span>}
                        <span style={{ marginLeft: 8, color: 'var(--text-muted)', fontSize: 13 }}>{m.specification} · {m.drug_form}</span>
                      </div>
                      <div style={{ fontSize: 14, color: 'var(--text-secondary)', whiteSpace: 'nowrap', marginLeft: 12 }}>
                        ¥{Number(m.price).toFixed(2)} · {m.stock}{m.unit}
                      </div>
                    </motion.div>
                  ))}
                </div>
              )}
            </>
          )}
        </motion.div>

        <motion.div style={{ display: 'flex', gap: 12 }} {...fadeUp} transition={{ delay: 0.2 }}>
          <motion.button className="glass-btn glass-btn--primary glass-btn--lg" type="submit" disabled={submitting} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
            {submitting ? '提交中...' : '提交处方'}
          </motion.button>
        </motion.div>
      </form>

      {/* 提交确认对话框 */}
      <AnimatePresence>
        {confirmOpen && (
          <motion.div className="confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="confirm-dialog glass-card" initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
              <h3>确认开具处方</h3>
              <div style={{ textAlign: 'left', margin: '16px 0', fontSize: 14, lineHeight: 2 }}>
                <div><strong>处方类型：</strong>{PRESCRIPTION_COLORS[prescriptionType].label}</div>
                <div><strong>病人：</strong>{selectedPatient?.name} ({selectedPatient?.gender} · {selectedPatient?.age}岁)</div>
                <div><strong>诊断：</strong><span style={{ color: 'var(--blue)' }}>{diagnosis}</span></div>
                <div><strong>药品数量：</strong>{items.length} 种</div>
                <div style={{ marginTop: 8, padding: '8px 12px', background: PRESCRIPTION_COLORS[prescriptionType].bg, border: `1px solid ${PRESCRIPTION_COLORS[prescriptionType].border}`, borderRadius: 8 }}>
                  {items.map((item, i) => (
                    <div key={i}>{item.medicine_name} — {item.trace_code} · {item.dosage} · {item.usage_method} · {item.frequency} × {item.days}天 × {item.quantity}{item.unit}</div>
                  ))}
                </div>
              </div>
              <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 20 }}>请仔细核对处方信息，提交后将进入药师审核流程。</p>
              <div className="confirm-actions">
                <motion.button className="glass-btn glass-btn--primary" onClick={confirmSubmit} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>确认提交</motion.button>
                <button className="glass-btn glass-btn--outline" onClick={() => setConfirmOpen(false)}>取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Medicine dosage modal */}
      <Modal isOpen={medModalOpen} onClose={() => { setMedModalOpen(false); setSelectedMed(null); }} title={selectedMed ? `添加药品: ${selectedMed.name}` : '添加药品'}>
        <div style={{ marginBottom: 12, fontSize: 14, color: 'var(--text-secondary)' }}>
          {selectedMed?.specification} · ¥{selectedMed ? Number(selectedMed.price).toFixed(2) : '0.00'}
        </div>
        <div className="form-grid form-grid--3">
          <div className="form-group">
            <label>用量 *</label>
            <input className="glass-input" placeholder="如 1片、10ml" value={medForm.dosage} onChange={(e) => setMedForm({ ...medForm, dosage: e.target.value })} autoFocus />
          </div>
          <div className="form-group">
            <label>追溯码 *</label>
            <input className="glass-input" placeholder="请输入该药品追溯码" value={medForm.trace_code} onChange={(e) => setMedForm({ ...medForm, trace_code: e.target.value })} />
          </div>
          <div className="form-group">
            <label>用法</label>
            <GlassSelect value={medForm.usage_method} options={USAGE_METHOD_OPTIONS} onChange={(usage_method) => setMedForm({ ...medForm, usage_method })} />
          </div>
          <div className="form-group">
            <label>频次</label>
            <GlassSelect value={medForm.frequency} options={FREQUENCY_OPTIONS} onChange={(frequency) => setMedForm({ ...medForm, frequency })} />
          </div>
          <div className="form-group"><label>天数</label><input className="glass-input" type="number" value={medForm.days} onChange={(e) => setMedForm({ ...medForm, days: parseInt(e.target.value) || 1 })} /></div>
          <div className="form-group"><label>数量</label><input className="glass-input" type="number" value={medForm.quantity} onChange={(e) => setMedForm({ ...medForm, quantity: parseInt(e.target.value) || 1 })} /></div>
          <div className="form-group"><label>备注</label><input className="glass-input" placeholder="如饭后服用" value={medForm.note} onChange={(e) => setMedForm({ ...medForm, note: e.target.value })} /></div>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <motion.button className="glass-btn glass-btn--success" type="button" onClick={addMedItem} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>确认添加</motion.button>
          <button className="glass-btn glass-btn--outline" type="button" onClick={() => { setMedModalOpen(false); setSelectedMed(null); }}>取消</button>
        </div>
      </Modal>
    </div>
  );
}
