import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { prescriptionApi } from '../services/api';
import type { Prescription } from '../types';
import { STATUS_LABELS, STATUS_COLORS } from '../types';
import { showToast } from '../components/Toast';
import ModuleIcon from '../components/ModuleIcon';
import { formatDateTime } from '../utils/date';

const rowAnim = {
  hidden: { opacity: 0, y: 10 },
  visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.05 } }),
};

export default function ReviewPage() {
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [confirmAction, setConfirmAction] = useState<{ id: number; status: 'approved' | 'rejected'; patientName: string } | null>(null);
  const pageSize = 10;

  const load = async (p: number) => {
    setLoading(true);
    try {
      const data = await prescriptionApi.list({ page: p, pageSize, status: 'pending' });
      setPrescriptions(data.list);
      setTotal(data.total);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(page); }, [page]);

  const totalPages = Math.ceil(total / pageSize);

  const currentActionPrescription = prescriptions.find(p => p.id === confirmAction?.id);

  const confirmReview = async () => {
    if (!confirmAction) return;
    const { id, status } = confirmAction;
    setConfirmAction(null);
    setActionLoading(id);
    try { const res = await prescriptionApi.review(id, status); showToast(res.message, status === 'approved' ? 'success' : 'warning'); load(page); }
    catch (err: any) { showToast(err.response?.data?.error || '操作失败', 'error'); }
    finally { setActionLoading(null); }
  };

  const handleReview = (id: number, status: 'approved' | 'rejected', patientName: string) => {
    setConfirmAction({ id, status, patientName });
  };

  return (
    <div>
      <motion.div className="page-header review-header" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div>
          <h1>处方审核</h1>
          <p>待审核处方列表，请仔细审核后操作</p>
        </div>
        <motion.div className="review-pending-card" whileHover={{ y: -3 }}>
          <ModuleIcon name="review" size={48} />
          <div>
            <div className="review-pending-value">{total}</div>
            <div className="review-pending-label">待审核</div>
          </div>
        </motion.div>
      </motion.div>

      <motion.div className="glass-card" style={{ padding: 20 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
        {loading ? (
          <div className="loading">加载中...</div>
        ) : prescriptions.length === 0 ? (
          <div className="empty-state"><div className="empty-icon"><ModuleIcon name="review" size={48} /></div><p>暂无待审核处方</p></div>
        ) : (
          <>
            <table className="glass-table" style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>处方编号</th>
                  <th>病人</th>
                  <th>诊断</th>
                  <th>医生</th>
                  <th className="review-time-cell">提交时间</th>
                  <th className="review-action-cell">操作</th>
                </tr>
              </thead>
              <tbody>
                <AnimatePresence>
                  {prescriptions.map((p, i) => (
                    <motion.tr key={p.id} variants={rowAnim} custom={i} initial="hidden" animate="visible" exit={{ opacity: 0 }}>
                      <td><strong>{p.prescription_code || `#${p.id}`}</strong></td>
                      <td><strong>{p.patient_name}</strong></td>
                      <td style={{ color: 'var(--blue)', fontWeight: 500 }}>{p.diagnosis}</td>
                      <td>{p.doctor_name}</td>
                      <td className="review-time-cell" style={{ color: 'var(--text-muted)', fontSize: 13 }}>{formatDateTime(p.created_at)}</td>
                      <td className="review-action-cell">
                        <div className="review-action-buttons">
                          <Link to={`/prescriptions/${p.id}`} className="glass-btn glass-btn--outline glass-btn--sm">查看详情</Link>
                          <motion.button className="glass-btn glass-btn--success glass-btn--sm" onClick={() => handleReview(p.id, 'approved', p.patient_name || '')} disabled={actionLoading === p.id} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
                            {actionLoading === p.id ? '...' : '通过'}
                          </motion.button>
                          <motion.button className="glass-btn glass-btn--danger glass-btn--sm" onClick={() => handleReview(p.id, 'rejected', p.patient_name || '')} disabled={actionLoading === p.id} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
                            {actionLoading === p.id ? '...' : '驳回'}
                          </motion.button>
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

      {/* 审核确认对话框 */}
      <AnimatePresence>
        {confirmAction && (
          <motion.div className="confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="confirm-dialog glass-card" initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
              <h3>{confirmAction.status === 'approved' ? '确认审核通过' : '确认驳回处方'}</h3>
              <div style={{ margin: '16px 0', fontSize: 14, lineHeight: 2 }}>
                <div><strong>处方编号：</strong>{currentActionPrescription?.prescription_code || `#${confirmAction.id}`}</div>
                <div><strong>病人：</strong>{confirmAction.patientName}</div>
                <div><strong>诊断：</strong><span style={{ color: 'var(--blue)' }}>{currentActionPrescription?.diagnosis}</span></div>
              </div>
              <p style={{ fontSize: 13, color: confirmAction.status === 'approved' ? 'var(--green)' : 'var(--red, #d9534f)', marginBottom: 20, fontWeight: 500 }}>
                {confirmAction.status === 'approved' ? '审核通过后，处方将进入发药流程。' : '驳回后处方将退回医生，请谨慎操作。'}
              </p>
              <div className="confirm-actions">
                <motion.button
                  className={`glass-btn ${confirmAction.status === 'approved' ? 'glass-btn--success' : 'glass-btn--danger'}`}
                  onClick={confirmReview}
                  whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}
                >
                  {confirmAction.status === 'approved' ? '确认通过' : '确认驳回'}
                </motion.button>
                <button className="glass-btn glass-btn--outline" onClick={() => setConfirmAction(null)}>取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
