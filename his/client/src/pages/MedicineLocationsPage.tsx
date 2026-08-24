import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { medicineLocationApi } from '../services/api';
import type { MedicineLocation, MedicineLocationFormData } from '../types';
import Modal from '../components/Modal';
import { showToast } from '../components/Toast';
import ModuleIcon from '../components/ModuleIcon';
import { formatDateTime } from '../utils/date';

const emptyForm: MedicineLocationFormData = { medicine_id: 0, medicine_name: '', x: 1, y: 1, z: 1 };

export default function MedicineLocationsPage() {
  const [locations, setLocations] = useState<MedicineLocation[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<MedicineLocationFormData>(emptyForm);
  const [submitting, setSubmitting] = useState(false);

  const load = async () => {
    setLoading(true);
    try { const data = await medicineLocationApi.list({ pageSize: 100 }); setLocations(data.list); }
    catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const openNew = () => { setEditId(null); setForm(emptyForm); setModalOpen(true); };

  const openEdit = (loc: MedicineLocation) => {
    setEditId(loc.id || null);
    setForm({ medicine_id: loc.medicine_id, medicine_name: loc.medicine_name, x: loc.x, y: loc.y, z: loc.z });
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (editId) { await medicineLocationApi.update(editId, form); }
      else { await medicineLocationApi.create(form); }
      setModalOpen(false); load();
    } catch (err: any) { showToast(err.response?.data?.error || '保存失败', 'error'); }
    finally { setSubmitting(false); }
  };

  return (
    <div>
      <motion.div className="page-header flex-between" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div className="page-title-with-icon">
          <span className="page-title-icon"><ModuleIcon name="medicineLocations" size={46} /></span>
          <div><h1>药品管理</h1><p>药品货架位置信息（medicine_locations）</p></div>
        </div>
        <motion.button className="glass-btn glass-btn--primary" onClick={openNew} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>＋ 新增位置</motion.button>
      </motion.div>

      <motion.div className="glass-card" style={{ padding: 20 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
        {loading ? <div className="loading">加载中...</div> :
         locations.length === 0 ? <div className="empty-state"><div className="empty-icon"><ModuleIcon name="medicineLocations" size={48} /></div><p>暂无位置数据</p></div> :
         <table className="glass-table medicine-location-table">
           <thead><tr><th>药品名称</th><th>X 轴</th><th>Y 轴</th><th>Z 轴</th><th>创建时间</th><th>操作</th></tr></thead>
           <tbody>
             {locations.map((loc) => (
               <tr key={loc.id}>
                 <td>
                   <strong>{loc.medicine_name}</strong>
                   {loc.trace_code_prefix && (
                     <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--blue)', background: 'rgba(74,144,217,0.1)', padding: '2px 6px', borderRadius: 4 }}>
                       {loc.trace_code_prefix}
                     </span>
                   )}
                 </td>
                 <td>{loc.x}</td><td>{loc.y}</td><td>{loc.z}</td>
                 <td style={{ color: 'var(--text-muted)', fontSize: 13 }}>{formatDateTime(loc.created_at)}</td>
                 <td>
                   <div className="action-btns">
                     <button className="glass-btn glass-btn--outline glass-btn--sm" onClick={() => openEdit(loc)}>编辑</button>
                   </div>
                 </td>
               </tr>
             ))}
           </tbody>
         </table>
        }
      </motion.div>

      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title={editId ? '编辑药品位置 (XYZ坐标)' : '新增药品位置'}>
        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            <div className="form-group"><label>药品ID</label><input className="glass-input" type="number" value={form.medicine_id} onChange={(e) => setForm({...form, medicine_id: Number(e.target.value)})} /></div>
            <div className="form-group"><label>药品名称</label><input className="glass-input" value={form.medicine_name} onChange={(e) => setForm({...form, medicine_name: e.target.value})} /></div>
            <div className="form-group"><label>X 坐标</label><input className="glass-input" type="number" step="0.1" value={form.x} onChange={(e) => setForm({...form, x: e.target.value === '' ? '' : Number(e.target.value)})} /></div>
            <div className="form-group"><label>Y 坐标</label><input className="glass-input" type="number" step="0.1" value={form.y} onChange={(e) => setForm({...form, y: e.target.value === '' ? '' : Number(e.target.value)})} /></div>
            <div className="form-group"><label>Z 坐标</label><input className="glass-input" type="number" step="0.1" value={form.z} onChange={(e) => setForm({...form, z: e.target.value === '' ? '' : Number(e.target.value)})} /></div>
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 20 }}>
            <motion.button className="glass-btn glass-btn--primary" type="submit" disabled={submitting} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>保存</motion.button>
            <button className="glass-btn glass-btn--outline" type="button" onClick={() => setModalOpen(false)}>取消</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
