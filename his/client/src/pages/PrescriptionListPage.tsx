import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { prescriptionApi } from '../services/api';
import type { Prescription } from '../types';
import { STATUS_LABELS, STATUS_COLORS, PRESCRIPTION_TYPE_LABELS } from '../types';
import ModuleIcon from '../components/ModuleIcon';
import GlassSelect from '../components/GlassSelect';
import { formatDateTime } from '../utils/date';

const STATUS_FILTERS = [
  { value: '', label: '全部' },
  { value: 'pending', label: '待审核' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' },
  { value: 'dispensed', label: '已发药' },
];

const PRESCRIPTION_TYPE_OPTIONS = [
  { value: '', label: '全部类型' },
  ...Object.entries(PRESCRIPTION_TYPE_LABELS).map(([value, label]) => ({ value, label })),
];

const rowAnim = {
  hidden: { opacity: 0, y: 10 },
  visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.04 } }),
};

export default function PrescriptionListPage() {
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [confirmDelete, setConfirmDelete] = useState<Prescription | null>(null);
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false);
  const pageSize = 10;

  const load = async (p: number, status: string, type: string) => {
    setLoading(true);
    try {
      const params: any = { page: p, pageSize };
      if (status) params.status = status;
      if (type) params.prescription_type = type;
      const data = await prescriptionApi.list(params);
      setPrescriptions(data.list);
      setTotal(data.total);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(page, statusFilter, typeFilter); }, [page, statusFilter, typeFilter]);

  const totalPages = Math.ceil(total / pageSize);

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await prescriptionApi.delete(confirmDelete.id);
      setConfirmDelete(null);
      load(page, statusFilter, typeFilter);
    } catch (err: any) { alert(err.response?.data?.error || '删除失败'); }
  };

  const handleDeleteAll = async () => {
    try {
      await prescriptionApi.deleteAll();
      setConfirmDeleteAll(false);
      setPage(1);
      load(1, statusFilter, typeFilter);
    } catch (err: any) { alert(err.response?.data?.error || '一键删除失败'); }
  };

  return (
    <div>
      <motion.div className="page-header flex-between" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div>
          <h1>处方记录</h1>
          <p>查看所有处方信息</p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
          <motion.button className="glass-btn glass-btn--danger glass-btn--sm" onClick={() => setConfirmDeleteAll(true)} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
            一键删除
          </motion.button>
          <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>只在测试阶段使用</span>
        </div>
      </motion.div>

      <motion.div className="flex-between" style={{ marginBottom: 16, gap: 12, flexWrap: 'wrap' }} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          {STATUS_FILTERS.map((f) => (
            <motion.button
              key={f.value}
              className={`glass-btn ${statusFilter === f.value ? 'glass-btn--primary' : 'glass-btn--outline'} glass-btn--sm`}
              onClick={() => { setPage(1); setStatusFilter(f.value); }}
              whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}
            >
              {f.label}
            </motion.button>
          ))}
        </div>
        <div style={{ width: 180 }}>
          <GlassSelect
            value={typeFilter}
            options={PRESCRIPTION_TYPE_OPTIONS}
            onChange={(v) => { setPage(1); setTypeFilter(v); }}
            placeholder="处方类型"
          />
        </div>
      </motion.div>

      <motion.div className="glass-card" style={{ padding: 20 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
        {loading ? (
          <div className="loading">加载中...</div>
        ) : prescriptions.length === 0 ? (
          <div className="empty-state"><div className="empty-icon"><ModuleIcon name="prescriptions" size={48} /></div><p>暂无处方记录</p></div>
        ) : (
          <>
            <table className="glass-table" style={{ width: '100%' }}>
              <thead>
                <tr><th>处方编号</th><th>病人</th><th>诊断</th><th>医生</th><th>状态</th><th style={{ textAlign: 'right' }}>时间</th><th>操作</th></tr>
              </thead>
              <tbody>
                <AnimatePresence>
                  {prescriptions.map((p, i) => (
                    <motion.tr key={p.id} variants={rowAnim} custom={i} initial="hidden" animate="visible" exit={{ opacity: 0 }}>
                      <td><strong>{p.prescription_code || `#${p.id}`}</strong></td>
                      <td>{p.patient_name}</td>
                      <td>{p.diagnosis}</td>
                      <td>{p.doctor_name}</td>
                      <td>
                        <span className="glass-badge" style={{ background: STATUS_COLORS[p.status] + '22', color: STATUS_COLORS[p.status] }}>
                          {STATUS_LABELS[p.status]}
                        </span>
                      </td>
                      <td style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'right' }}>{formatDateTime(p.created_at)}</td>
                      <td>
                        <div className="action-btns">
                          <Link to={`/prescriptions/${p.id}`} className="glass-btn glass-btn--outline glass-btn--sm">查看</Link>
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

      <AnimatePresence>
        {confirmDelete && (
          <motion.div className="confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="confirm-dialog glass-card" initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
              <h3>确认删除</h3>
              <p>确定要删除处方 {confirmDelete.prescription_code || `#${confirmDelete.id}`} 及其所有药品明细吗？此操作不可撤销。</p>
              <div className="confirm-actions">
                <motion.button className="glass-btn glass-btn--danger" onClick={handleDelete} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>确认删除</motion.button>
                <button className="glass-btn glass-btn--outline" onClick={() => setConfirmDelete(null)}>取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {confirmDeleteAll && (
          <motion.div className="confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="confirm-dialog glass-card" initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
              <h3>确认一键删除</h3>
              <p>确定要删除所有处方及其所有药品明细吗？此操作不可撤销。</p>
              <div className="confirm-actions">
                <motion.button className="glass-btn glass-btn--danger" onClick={handleDeleteAll} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>确认一键删除</motion.button>
                <button className="glass-btn glass-btn--outline" onClick={() => setConfirmDeleteAll(false)}>取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
