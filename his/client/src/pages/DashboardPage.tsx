import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { prescriptionApi, patientApi, medicineApi } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { STATUS_LABELS } from '../types';
import ModuleIcon from '../components/ModuleIcon';
import { DASHBOARD_MODULES } from '../data/dashboardModules';
import { formatDateTime } from '../utils/date';

const STATUS_COLORS: Record<string,string> = {
  pending:'badge-warning', approved:'badge-success', rejected:'badge-danger', dispensed:'badge-info',
};

export default function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [pendingCount, setPendingCount] = useState(0);
  const [medicineCount, setMedicineCount] = useState(0);
  const [patientCount, setPatientCount] = useState(0);
  const [recents, setRecents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [p, m, pt, ps] = await Promise.all([
          prescriptionApi.list({ page:1, pageSize:1, status:'pending' }),
          medicineApi.list({ page:1, pageSize:1 }),
          patientApi.list({ page:1, pageSize:1 }),
          prescriptionApi.list({ page:1, pageSize:5 }),
        ]);
        setPendingCount(p.total); setMedicineCount(m.total);
        setPatientCount(pt.total); setRecents(ps.list);
      } catch(e) { console.error(e); }
      finally { setLoading(false); }
    })();
  }, []);

  return (
    <div>
      <div className="page-header">
        <h2>工作版</h2>
        <p>欢迎回来，{user?.real_name}</p>
      </div>

      {/* 12 modules */}
      <div className="card mb" style={{ padding:16 }}>
        <div className="module-grid">
          {DASHBOARD_MODULES.map((m, i) => (
            <motion.div
              key={m.key} className={`module-item ${!m.available?'disabled':''}`}
              initial={{ opacity:0, y:12 }} animate={{ opacity:1, y:0 }}
              transition={{ delay:i*0.03 }} whileHover={!m.available?{}:{ scale:1.03 }}
              onClick={() => { if(m.available && m.to) navigate(m.to); }}
              aria-disabled={!m.available}
            >
              <span className="module-icon"><ModuleIcon name={m.key} /></span>
              <span className="module-label">{m.label}</span>
              {!m.available && <span className="module-status">未开放</span>}
            </motion.div>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div className="stat-row">
        <motion.div className="card stat-card" initial={{ opacity:0 }} animate={{ opacity:1 }} transition={{ delay:0.3 }}>
          <div className="stat-icon"><ModuleIcon name="pending" size={54} /></div>
          <div className="stat-value" style={{ color:'#D97706' }}>{pendingCount}</div>
          <div className="stat-label">待审核 / 临时医嘱</div>
        </motion.div>
        <motion.div className="card stat-card" initial={{ opacity:0 }} animate={{ opacity:1 }} transition={{ delay:0.35 }}>
          <div className="stat-icon"><ModuleIcon name="medicineTotal" size={54} /></div>
          <div className="stat-value" style={{ color:'var(--primary)' }}>{medicineCount}</div>
          <div className="stat-label">药品总类</div>
        </motion.div>
        <motion.div className="card stat-card" initial={{ opacity:0 }} animate={{ opacity:1 }} transition={{ delay:0.4 }}>
          <div className="stat-icon"><ModuleIcon name="patientTotal" size={54} /></div>
          <div className="stat-value" style={{ color:'#16A34A' }}>{patientCount}</div>
          <div className="stat-label">在册病人</div>
        </motion.div>
      </div>

      {/* Recent prescriptions */}
      {!loading && recents.length > 0 && (
        <motion.div className="card" initial={{ opacity:0, y:16 }} animate={{ opacity:1, y:0 }} transition={{ delay:0.45 }}>
          <h3 style={{ fontSize:16, fontWeight:600, marginBottom:12 }}>最近处方</h3>
          <table className="table" style={{ width: '100%' }}>
            <thead><tr><th style={{ textAlign: 'center', paddingRight: '3.5%' }}>处方编号</th><th style={{ textAlign: 'center' }}>病人</th><th style={{ textAlign: 'center' }}>诊断</th><th style={{ textAlign: 'center' }}>医生</th><th style={{ textAlign: 'center' }}>状态</th><th style={{ textAlign: 'center', paddingLeft: '2.5%' }}>时间</th></tr></thead>
            <tbody>
              {recents.map((p:any) => (
                <tr key={p.id} style={{ cursor:'pointer' }} onClick={() => navigate(`/prescriptions/${p.id}`)}>
                  <td style={{ textAlign: 'center', paddingRight: '3.5%' }}><strong style={{ fontSize: 13 }}>{p.prescription_code || `#${p.id}`}</strong></td>
                  <td style={{ textAlign: 'center' }}>{p.patient_name}</td>
                  <td style={{ textAlign: 'center' }}>{(p.diagnosis||'').slice(0,16)}{(p.diagnosis||'').length>16?'...':''}</td>
                  <td style={{ textAlign: 'center' }}>{p.doctor_name}</td>
                  <td style={{ textAlign: 'center' }}><span className={`badge ${STATUS_COLORS[p.status]}`}>{STATUS_LABELS[p.status]}</span></td>
                  <td style={{ textAlign: 'center', paddingLeft: '2.5%', color:'var(--text-secondary)', fontSize:13 }}>{formatDateTime(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </motion.div>
      )}
    </div>
  );
}
