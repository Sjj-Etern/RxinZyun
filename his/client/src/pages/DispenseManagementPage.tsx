import { useEffect, useState } from 'react';
import api, { prescriptionApi } from '../services/api';
import type { Prescription } from '../types';
import { showToast } from '../components/Toast';
import { formatDateTime } from '../utils/date';

export default function DispenseManagementPage() {
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [robots, setRobots] = useState<any[]>([]);
  const [robotCodes, setRobotCodes] = useState<Record<number, string>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [prescriptionRes, robotRes] = await Promise.all([
        prescriptionApi.list({ page: 1, pageSize: 200, status: 'approved' }),
        api.get('/robots'),
      ]);
      setPrescriptions(prescriptionRes.list);
      setRobots(robotRes.data);
    } catch (err: any) {
      showToast(err.response?.data?.error || '发药管理数据加载失败', 'error');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);
  const availableRobots = robots.filter(robot => robot.status === 'available');

  const dispense = async (prescription: Prescription) => {
    const robotCode = (robotCodes[prescription.id] || '').trim();
    if (!robotCode) return showToast('请输入或选择机器人设备编号', 'error');
    setBusyId(prescription.id);
    try {
      const response = await api.put(`/prescriptions/${prescription.id}/dispense`, { robot_code: robotCode });
      showToast(response.data.message || '已开始配送', 'success');
      await load();
    } catch (err: any) {
      showToast(err.response?.data?.error || '发药确认失败', 'error');
    } finally { setBusyId(null); }
  };

  return (
    <div>
      <style>{'.dispense-management-table th, .dispense-management-table td { height: 60px; text-align: center !important; vertical-align: middle !important; } .dispense-management-table th { height: 52px; } .dispense-management-table input { text-align: center; }'}</style>
      <div className="page-header">
        <h1>发药管理</h1>
        <p>确认药品已配齐后，选择空闲机器人开始配送。</p>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 260px', gap: 16, marginBottom: 18 }}>
        <div className="glass-card" style={{ padding: 20, borderLeft: '4px solid #38BFC1' }}>
          <div style={{ fontSize: 30, fontWeight: 700, color: '#168a8d' }}>{prescriptions.length}</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>待确认发药处方</div>
        </div>
        <div className="glass-card" style={{ padding: 20, borderLeft: '4px solid #22c55e' }}>
          <div style={{ fontSize: 30, fontWeight: 700, color: '#15803d' }}>{availableRobots.length}</div>
          <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>可选择的空闲机器人</div>
        </div>
      </div>
      <div className="glass-card" style={{ padding: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <strong style={{ fontSize: 16 }}>待发药列表</strong>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>输入设备编号或从下拉建议中选择；配送开始后不可重复发药。</div>
          </div>
          <button className="glass-btn glass-btn--outline glass-btn--sm" onClick={load}>刷新</button>
        </div>
        {loading ? (
          <div className="loading">加载中...</div>
        ) : !prescriptions.length ? (
          <div className="empty-state"><p>暂无待确认发药处方</p></div>
        ) : (
          <table className="glass-table dispense-management-table" style={{ width: '100%' }}>
            <thead>
              <tr>
                <th style={{ verticalAlign: 'middle' }}>处方编号</th>
                <th style={{ verticalAlign: 'middle' }}>病人</th>
                <th style={{ verticalAlign: 'middle' }}>诊断</th>
                <th style={{ verticalAlign: 'middle' }}>提交时间</th>
                <th style={{ verticalAlign: 'middle', minWidth: 210 }}>机器人设备编号</th>
                <th style={{ verticalAlign: 'middle' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {prescriptions.map(p => (
                <tr key={p.id}>
                  <td style={{ verticalAlign: 'middle' }}><strong>{p.prescription_code || `#${p.id}`}</strong></td>
                  <td style={{ verticalAlign: 'middle' }}>{p.patient_name || '-'}</td>
                  <td style={{ verticalAlign: 'middle' }}>{p.diagnosis}</td>
                  <td style={{ verticalAlign: 'middle', color: 'var(--text-muted)', fontSize: 13 }}>{formatDateTime(p.created_at)}</td>
                  <td style={{ verticalAlign: 'middle' }}>
                    <input
                      className="glass-input"
                      list={`robot-codes-${p.id}`}
                      value={robotCodes[p.id] || ''}
                      onChange={e => setRobotCodes(prev => ({ ...prev, [p.id]: e.target.value.toUpperCase() }))}
                      placeholder="例如 R001"
                      style={{ width: '100%', minWidth: 160 }}
                    />
                    <datalist id={`robot-codes-${p.id}`}>
                      {availableRobots.map(robot => (
                        <option key={robot.id} value={robot.code}>{robot.name}</option>
                      ))}
                    </datalist>
                  </td>
                  <td style={{ verticalAlign: 'middle' }}>
                    <button
                      className="glass-btn glass-btn--primary glass-btn--sm"
                      disabled={busyId === p.id}
                      onClick={() => dispense(p)}
                    >
                      {busyId === p.id ? '正在确认…' : '确认发药'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}