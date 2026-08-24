import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { patientApi } from '../services/api';
import type { Patient, PatientFormData } from '../types';
import Modal from '../components/Modal';
import { showToast } from '../components/Toast';
import ModuleIcon from '../components/ModuleIcon';
import GlassSelect from '../components/GlassSelect';
import { formatDateTime } from '../utils/date';

const emptyForm: PatientFormData = { name: '', gender: '男', age: '', phone: '', id_card: '', address: '' };
const GENDER_OPTIONS = [
  { value: '男', label: '男' },
  { value: '女', label: '女' },
];

const rowAnim = {
  hidden: { opacity: 0, y: 10 },
  visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.04 } }),
};

export default function PatientListPage() {
  const navigate = useNavigate();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<PatientFormData>(emptyForm);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Patient | null>(null);
  const pageSize = 10;

  const loadPatients = async (p: number, kw: string) => {
    setLoading(true);
    try {
      const data = await patientApi.list({ page: p, pageSize, keyword: kw });
      setPatients(data.list);
      setTotal(data.total);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadPatients(page, keyword); }, [page, keyword]);

  const totalPages = Math.ceil(total / pageSize);
  const update = (key: keyof PatientFormData, value: string) => setForm((prev) => ({ ...prev, [key]: value }));

  const openNew = () => { setEditId(null); setForm(emptyForm); setError(''); setModalOpen(true); };

  const openEdit = (p: Patient) => {
    setEditId(p.id);
    setForm({ name: p.name, gender: p.gender, age: p.age || '', phone: p.phone || '', id_card: p.id_card || '', address: p.address || '' });
    setError('');
    setModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name || !form.gender) { setError('姓名和性别为必填项'); return; }
    setSubmitting(true); setError('');
    try {
      if (editId) {
        await patientApi.update(editId, form);
      } else {
        const res = await patientApi.create(form);
        setModalOpen(false);
        navigate(`/patients/${res.id}`);
        return;
      }
      setModalOpen(false);
      loadPatients(page, keyword);
    } catch (err: any) { setError(err.response?.data?.error || '保存失败'); }
    finally { setSubmitting(false); }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await patientApi.delete(confirmDelete.id);
      setConfirmDelete(null);
      loadPatients(page, keyword);
    } catch (err: any) { showToast(err.response?.data?.error || '删除失败', 'error'); }
  };

  return (
    <div>
      <motion.div className="page-header flex-between" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div>
          <h1>病人管理</h1>
          <p>管理在册病人信息</p>
        </div>
        <motion.button className="glass-btn glass-btn--primary" onClick={openNew} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
          ＋ 新增病人
        </motion.button>
      </motion.div>

      <motion.div className="search-bar" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
        <input className="glass-input" placeholder="搜索姓名或手机号..." value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (setPage(1), loadPatients(1, keyword))} />
        <button className="glass-btn glass-btn--primary" onClick={() => { setPage(1); loadPatients(1, keyword); }}>搜索</button>
      </motion.div>

      {/* Form Modal */}
      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title={editId ? '编辑病人' : '新增病人'}>
        {error && <div className="alert alert--error">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            <div className="form-group">
              <label>姓名 *</label>
              <input className="glass-input" value={form.name} onChange={(e) => update('name', e.target.value)} placeholder="请输入姓名" />
            </div>
            <div className="form-group">
              <label>性别 *</label>
              <GlassSelect value={form.gender} options={GENDER_OPTIONS} onChange={(value) => update('gender', value)} />
            </div>
            <div className="form-group">
              <label>年龄</label>
              <input className="glass-input" type="number" value={form.age} onChange={(e) => update('age', e.target.value)} placeholder="请输入年龄" />
            </div>
            <div className="form-group">
              <label>手机号</label>
              <input className="glass-input" value={form.phone} onChange={(e) => update('phone', e.target.value)} placeholder="请输入手机号" />
            </div>
            <div className="form-group">
              <label>身份证号</label>
              <input className="glass-input" value={form.id_card} onChange={(e) => update('id_card', e.target.value)} placeholder="请输入身份证号" />
            </div>
            <div className="form-group">
              <label>地址</label>
              <input className="glass-input" value={form.address} onChange={(e) => update('address', e.target.value)} placeholder="请输入地址" />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 20 }}>
            <motion.button className="glass-btn glass-btn--primary" type="submit" disabled={submitting} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              {submitting ? '保存中...' : '保存病人信息'}
            </motion.button>
            <button className="glass-btn glass-btn--outline" type="button" onClick={() => setModalOpen(false)}>取消</button>
          </div>
        </form>
      </Modal>

      {/* Table */}
      <motion.div className="glass-card" style={{ padding: 20 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
        {loading ? (
          <div className="loading">加载中...</div>
        ) : patients.length === 0 ? (
          <div className="empty-state"><div className="empty-icon"><ModuleIcon name="patients" size={48} /></div><p>暂无病人数据</p></div>
        ) : (
          <>
            <table className="glass-table patient-table">
              <thead>
                <tr><th>姓名</th><th>性别</th><th>年龄</th><th>手机号</th><th>地址</th><th>创建时间</th><th>操作</th></tr>
              </thead>
              <tbody>
                <AnimatePresence>
                  {patients.map((p, i) => (
                    <motion.tr key={p.id} variants={rowAnim} custom={i} initial="hidden" animate="visible" exit={{ opacity: 0 }}>
                      <td><strong>{p.name}</strong></td>
                      <td>{p.gender}</td>
                      <td>{p.age}</td>
                      <td>{p.phone || '-'}</td>
                      <td style={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{p.address || '-'}</td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 13 }}>{formatDateTime(p.created_at)}</td>
                      <td>
                        <div className="action-btns">
                          <Link to={`/patients/${p.id}`} className="glass-btn glass-btn--outline glass-btn--sm">查看</Link>
                          <motion.button className="glass-btn glass-btn--outline glass-btn--sm" onClick={() => openEdit(p)} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>编辑</motion.button>
                          <motion.button className="glass-btn glass-btn--danger glass-btn--sm" onClick={() => setConfirmDelete(p)} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>删除</motion.button>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </AnimatePresence>
              </tbody>
            </table>
            {totalPages > 1 && (
              <div className="pagination">
                <button disabled={page <= 1} onClick={() => setPage(page - 1)}>上一页</button>
                <span className="page-info">第 {page} / {totalPages} 页（共 {total} 条）</span>
                <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>下一页</button>
              </div>
            )}
          </>
        )}
      </motion.div>

      {/* Confirm delete */}
      <AnimatePresence>
        {confirmDelete && (
          <motion.div className="confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="confirm-dialog glass-card" initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
              <h3>确认删除</h3>
              <p>确定要删除病人「{confirmDelete.name}」及其所有处方记录吗？此操作不可撤销。</p>
              <div className="confirm-actions">
                <motion.button className="glass-btn glass-btn--danger" onClick={handleDelete} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>确认删除</motion.button>
                <button className="glass-btn glass-btn--outline" onClick={() => setConfirmDelete(null)}>取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
