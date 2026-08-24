import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { patientApi } from '../services/api';
import type { Patient, PatientFormData } from '../types';
import { STATUS_LABELS, STATUS_COLORS } from '../types';
import Modal from '../components/Modal';
import ModuleIcon from '../components/ModuleIcon';
import GlassSelect from '../components/GlassSelect';
import { formatDateTime } from '../utils/date';

const rowAnim = {
  hidden: { opacity: 0, x: -10 },
  visible: (i: number) => ({ opacity: 1, x: 0, transition: { delay: i * 0.06 } }),
};
const GENDER_OPTIONS = [
  { value: '男', label: '男' },
  { value: '女', label: '女' },
];

export default function PatientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [patient, setPatient] = useState<Patient | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState<PatientFormData>({ name: '', gender: '男', age: '', phone: '', id_card: '', address: '' });
  const [submitting, setSubmitting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const load = async () => {
    try {
      const data = await patientApi.getById(Number(id));
      setPatient(data);
    } catch (err: any) { setError(err.response?.data?.error || '加载失败'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [id]);

  const openEdit = () => {
    if (!patient) return;
    setForm({ name: patient.name, gender: patient.gender, age: patient.age || '', phone: patient.phone || '', id_card: patient.id_card || '', address: patient.address || '' });
    setModalOpen(true);
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.gender) return;
    setSubmitting(true);
    try {
      await patientApi.update(Number(id), form);
      setModalOpen(false);
      load();
    } catch (err: any) { alert(err.response?.data?.error || '保存失败'); }
    finally { setSubmitting(false); }
  };

  const handleDelete = async () => {
    try {
      await patientApi.delete(Number(id));
      window.location.href = '/patients';
    } catch (err: any) { alert(err.response?.data?.error || '删除失败'); }
  };

  if (loading) return <div className="loading">加载中...</div>;
  if (error) return <div className="alert alert--error">{error}</div>;
  if (!patient) return <div className="alert alert--error">病人不存在</div>;

  return (
    <div>
      <motion.div className="page-header flex-between" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div>
          <h1>{patient.name} 的病历信息</h1>
          <p>编号 #{patient.id} · {patient.gender} · {patient.age}岁</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Link to="/patients" className="glass-btn glass-btn--outline">返回列表</Link>
          <motion.button className="glass-btn glass-btn--outline" onClick={openEdit} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>编辑信息</motion.button>
          <motion.button className="glass-btn glass-btn--danger" onClick={() => setConfirmDelete(true)} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>删除病人</motion.button>
          <Link to="/prescriptions/new" className="glass-btn glass-btn--primary">为此病人开方</Link>
        </div>
      </motion.div>

      <motion.div className="glass-card" style={{ padding: 20, marginBottom: 20 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
        <h3 style={{ marginBottom: 16, fontSize: 16, fontWeight: 600 }}>基本信息</h3>
        <div className="form-grid form-grid--3" style={{ fontSize: 14 }}>
          <div><span style={{ color: 'var(--text-muted)' }}>姓名：</span>{patient.name}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>性别：</span>{patient.gender}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>年龄：</span>{patient.age || '-'}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>手机号：</span>{patient.phone || '-'}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>身份证号：</span>{patient.id_card || '-'}</div>
          <div><span style={{ color: 'var(--text-muted)' }}>地址：</span>{patient.address || '-'}</div>
        </div>
      </motion.div>

      <motion.div className="glass-card" style={{ padding: 20 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <h3 style={{ marginBottom: 16, fontSize: 16, fontWeight: 600 }}>历史处方（{patient.prescriptions?.length || 0}）</h3>
        {!patient.prescriptions || patient.prescriptions.length === 0 ? (
          <div className="empty-state"><div className="empty-icon"><ModuleIcon name="prescriptions" size={48} /></div><p>暂无处方记录</p></div>
        ) : (
          <table className="glass-table">
            <thead>
              <tr><th>处方编号</th><th>诊断</th><th>医生</th><th>状态</th><th>时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              {patient.prescriptions.map((p: any, i: number) => (
                <motion.tr key={p.id} variants={rowAnim} custom={i} initial="hidden" animate="visible">
                  <td>#{p.id}</td>
                  <td>{p.diagnosis}</td>
                  <td>{p.doctor_name}</td>
                  <td>
                    <span className="glass-badge" style={{ background: STATUS_COLORS[p.status] + '22', color: STATUS_COLORS[p.status] }}>
                      {STATUS_LABELS[p.status]}
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-muted)', fontSize: 13 }}>{formatDateTime(p.created_at)}</td>
                  <td>
                    <Link to={`/prescriptions/${p.id}`} className="glass-btn glass-btn--outline glass-btn--sm">查看</Link>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </motion.div>

      {/* Edit Modal */}
      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title="编辑病人信息">
        <form onSubmit={handleUpdate}>
          <div className="form-grid">
            <div className="form-group"><label>姓名 *</label><input className="glass-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
            <div className="form-group"><label>性别 *</label><GlassSelect value={form.gender} options={GENDER_OPTIONS} onChange={(gender) => setForm({ ...form, gender })} /></div>
            <div className="form-group"><label>年龄</label><input className="glass-input" type="number" value={form.age} onChange={(e) => setForm({ ...form, age: e.target.value === '' ? '' : Number(e.target.value) })} /></div>
            <div className="form-group"><label>手机号</label><input className="glass-input" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></div>
            <div className="form-group"><label>身份证号</label><input className="glass-input" value={form.id_card} onChange={(e) => setForm({ ...form, id_card: e.target.value })} /></div>
            <div className="form-group"><label>地址</label><input className="glass-input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></div>
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 20 }}>
            <motion.button className="glass-btn glass-btn--primary" type="submit" disabled={submitting} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>{submitting ? '保存中...' : '保存'}</motion.button>
            <button className="glass-btn glass-btn--outline" type="button" onClick={() => setModalOpen(false)}>取消</button>
          </div>
        </form>
      </Modal>

      {/* Confirm delete */}
      <AnimatePresence>
        {confirmDelete && (
          <motion.div className="confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="confirm-dialog glass-card" initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
              <h3>确认删除</h3>
              <p>确定要删除病人「{patient.name}」及其所有处方记录吗？此操作不可撤销。</p>
              <div className="confirm-actions">
                <motion.button className="glass-btn glass-btn--danger" onClick={handleDelete} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>确认删除</motion.button>
                <button className="glass-btn glass-btn--outline" onClick={() => setConfirmDelete(false)}>取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
