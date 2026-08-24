import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import api, { prescriptionApi } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import type { Prescription } from '../types';
import { STATUS_LABELS, STATUS_COLORS } from '../types';
import { showToast } from '../components/Toast';
import { formatDateTime } from '../utils/date';

const rowAnim = {
  hidden: { opacity: 0, x: -10 },
  visible: (i: number) => ({ opacity: 1, x: 0, transition: { delay: i * 0.06 } }),
};

export default function PrescriptionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmDispenseOpen, setConfirmDispenseOpen] = useState(false);

  const load = async () => {
    try { const data = await prescriptionApi.getById(Number(id)); setPrescription(data); }
    catch (err: any) { setError(err.response?.data?.error || '加载失败'); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [id]);

  const confirmDispense = async () => {
    const robotId = window.prompt('请输入空闲配送机器人 ID（可在机器人管理中查看）');
    if (!robotId || !Number(robotId)) return;
    setConfirmDispenseOpen(false);
    setActionLoading(true);
    try { const res = await api.put(`/prescriptions/${id}/dispense`, { robot_id: Number(robotId) }); showToast(res.data.message || '已开始配送', 'success'); load(); }
    catch (err: any) { showToast(err.response?.data?.error || '操作失败', 'error'); }
    finally { setActionLoading(false); }
  };

  const handleDelete = async () => {
    try { await prescriptionApi.delete(Number(id)); showToast('处方已删除', 'info'); setTimeout(() => { window.location.href = '/prescriptions'; }, 600); }
    catch (err: any) { showToast(err.response?.data?.error || '删除失败', 'error'); }
  };

  if (loading) return <div className="loading">加载中...</div>;
  if (error) return <div className="alert alert--error">{error}</div>;
  if (!prescription) return <div className="alert alert--error">处方不存在</div>;

  const canDispense = (user?.role === 'pharmacist' || user?.role === 'admin') && prescription.status === 'approved';

  return (
    <div>
      <motion.div className="page-header flex-between" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div>
          <h1>处方详情 {prescription.prescription_code || `#${prescription.id}`}</h1>
          <p>
            <span className="glass-badge" style={{ background: STATUS_COLORS[prescription.status] + '22', color: STATUS_COLORS[prescription.status], fontSize: 13 }}>
              {STATUS_LABELS[prescription.status]}
            </span>
            <span style={{ marginLeft: 8, color: 'var(--text-muted)', fontSize: 13 }}>{formatDateTime(prescription.created_at)}</span>
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <Link to="/prescriptions" className="glass-btn glass-btn--outline">返回列表</Link>
          <motion.button className="glass-btn glass-btn--danger glass-btn--sm" onClick={() => setConfirmDelete(true)} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>删除处方</motion.button>
        </div>
      </motion.div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        <motion.div className="glass-card" style={{ padding: 20 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>病人信息</h3>
          <div style={{ fontSize: 14, lineHeight: 2 }}>
            <div><span style={{ color: 'var(--text-muted)' }}>姓名：</span><strong>{prescription.patient_name}</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>性别：</span>{prescription.patient_gender}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>年龄：</span>{prescription.patient_age}岁</div>
          </div>
          <Link to={`/patients/${prescription.patient_id}`} className="glass-btn glass-btn--outline glass-btn--sm mt-md" style={{ display: 'inline-flex' }}>查看病历</Link>
        </motion.div>

        <motion.div className="glass-card" style={{ padding: 20 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>诊断信息</h3>
          <div style={{ fontSize: 14, lineHeight: 2 }}>
            <div><span style={{ color: 'var(--text-muted)' }}>诊断：</span><strong style={{ color: 'var(--blue)' }}>{prescription.diagnosis}</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>开方医生：</span>{prescription.doctor_name}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>备注：</span>{prescription.note || '-'}</div>
          </div>
        </motion.div>
      </div>

      <motion.div className="glass-card" style={{ padding: 20, marginTop: 16 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>处方明细</h3>
        {!prescription.items || prescription.items.length === 0 ? (
          <div className="empty-state"><p>无药品明细</p></div>
        ) : (
          <table className="glass-table">
            <thead>
              <tr><th>药品名称</th><th>追溯码</th><th>规格</th><th>用量</th><th>用法</th><th>频次</th><th>天数</th><th>数量</th><th>备注</th></tr>
            </thead>
            <tbody>
              {prescription.items.map((item, i) => (
                <motion.tr key={item.id} variants={rowAnim} custom={i} initial="hidden" animate="visible">
                  <td><strong>{item.medicine_name}</strong></td>
                  <td><code style={{ fontSize: 11, wordBreak: 'break-all' }}>{item.trace_code || '-'}</code></td>
                  <td style={{ fontSize: 13 }}>{item.specification}</td>
                  <td>{item.dosage}</td>
                  <td>{item.usage_method}</td>
                  <td>{item.frequency}</td>
                  <td>{item.days}天</td>
                  <td>{item.quantity}{item.unit}</td>
                  <td style={{ color: 'var(--text-muted)', fontSize: 13 }}>{item.note || '-'}</td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        )}
      </motion.div>

      {canDispense && (
        <motion.div className="glass-card" style={{ padding: 20, marginTop: 16, display: 'flex', gap: 12, alignItems: 'center' }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <span style={{ fontWeight: 600, marginRight: 8 }}>操作：</span>
          <motion.button className="glass-btn glass-btn--primary" onClick={() => setConfirmDispenseOpen(true)} disabled={actionLoading} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>确认发药</motion.button>
        </motion.div>
      )}

      {/* 发药确认对话框 */}
      <AnimatePresence>
        {confirmDispenseOpen && (
          <motion.div className="confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="confirm-dialog glass-card" initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
              <h3>确认发药</h3>
              <div style={{ margin: '16px 0', fontSize: 14, lineHeight: 2 }}>
                <div><strong>处方编号：</strong>{prescription.prescription_code || `#${prescription.id}`}</div>
                <div><strong>病人：</strong>{prescription.patient_name}</div>
                <div><strong>诊断：</strong><span style={{ color: 'var(--blue)' }}>{prescription.diagnosis}</span></div>
              </div>
              <p style={{ fontSize: 13, color: 'var(--green)', marginBottom: 20, fontWeight: 500 }}>确认药品已发放给患者？操作后处方状态将变为"已发药"。</p>
              <div className="confirm-actions">
                <motion.button className="glass-btn glass-btn--primary" onClick={confirmDispense} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>确认发药</motion.button>
                <button className="glass-btn glass-btn--outline" onClick={() => setConfirmDispenseOpen(false)}>取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {confirmDelete && (
          <motion.div className="confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="confirm-dialog glass-card" initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
              <h3>确认删除</h3>
              <p>确定要删除处方 {prescription.prescription_code || `#${prescription.id}`} 及其所有药品明细吗？此操作不可撤销。</p>
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
