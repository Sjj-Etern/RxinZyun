import { FormEvent, useEffect, useMemo, useState } from 'react';
import api from '../services/api';
import { showToast } from '../components/Toast';
import { useAuth } from '../hooks/useAuth';

const statusMeta: Record<string, { label: string; color: string; background: string }> = {
  available: { label: '空闲可调度', color: '#15803d', background: 'rgba(34,197,94,.12)' },
  busy: { label: '配送任务中', color: '#0369a1', background: 'rgba(14,165,233,.12)' },
  disabled: { label: '已停用', color: '#6b7280', background: 'rgba(107,114,128,.12)' },
};

export default function RobotPage() {
  const { user } = useAuth();
  const [robots, setRobots] = useState<any[]>([]);
  const [form, setForm] = useState({ code: '', name: '', status: 'available' });
  const [editing, setEditing] = useState<number | null>(null);

  const load = () => api.get('/robots').then(r => setRobots(r.data)).catch(() => showToast('机器人列表加载失败', 'error'));
  useEffect(() => { load(); }, []);

  const counts = useMemo(() => ({
    available: robots.filter(r => r.status === 'available').length,
    busy: robots.filter(r => r.status === 'busy').length,
    disabled: robots.filter(r => r.status === 'disabled').length,
  }), [robots]);

  const reset = () => { setEditing(null); setForm({ code: '', name: '', status: 'available' }); };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const response = editing ? await api.put(`/robots/${editing}`, form) : await api.post('/robots', form);
      showToast(response.data.message || (editing ? '机器人已更新' : '机器人已新增'), 'success');
      reset(); load();
    } catch (err: any) { showToast(err.response?.data?.error || '保存失败', 'error'); }
  };

  const remove = async (id: number) => {
    if (!window.confirm('确认删除此机器人？')) return;
    try {
      showToast((await api.delete(`/robots/${id}`)).data.message, 'success');
      load();
    } catch (e: any) { showToast(e.response?.data?.error || '删除失败', 'error'); }
  };

  const restoreAvailable = async (robot: any) => {
    try {
      const response = await api.put(`/robots/${robot.id}`, { code: robot.code, name: robot.name, status: 'available' });
      showToast(response.data.message || `测试阶段：已恢复 ${robot.code} 为空闲状态`, 'success');
      load();
    } catch (e: any) { showToast(e.response?.data?.error || '恢复空闲状态失败', 'error'); }
  };

  return (
    <div>
      <style>{'.robot-management-table th, .robot-management-table td { height: 60px; text-align: center !important; vertical-align: middle !important; } .robot-management-table th { height: 52px; }'}</style>
      <div className="page-header">
        <h1>机器人管理</h1>
        <p>查看可调度状态；药师发药时从空闲机器人中选择配送设备。</p>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 14, marginBottom: 18 }}>
        {Object.entries(counts).map(([key, count]) => (
          <div key={key} className="glass-card" style={{ padding: 18, borderTop: `3px solid ${statusMeta[key].color}` }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: statusMeta[key].color }}>{count}</div>
            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{statusMeta[key].label}</div>
          </div>
        ))}
      </div>
      {user?.role === 'admin' && (
        <form className="glass-card" onSubmit={submit} style={{ padding: 20, marginBottom: 18 }}>
          <div style={{ fontWeight: 650, marginBottom: 14 }}>{editing ? '编辑机器人' : '新增机器人'}</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.4fr 1fr auto', gap: 10, alignItems: 'center' }}>
            <input className="glass-input" placeholder="编号，例如 R003" value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} />
            <input className="glass-input" placeholder="机器人名称" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} />
            <select className="glass-input" value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}>
              {Object.entries(statusMeta).map(([key, value]) => (
                <option key={key} value={key}>{value.label}</option>
              ))}
            </select>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="glass-btn glass-btn--primary">{editing ? '保存' : '新增'}</button>
              {editing && <button type="button" className="glass-btn glass-btn--outline" onClick={reset}>取消</button>}
            </div>
          </div>
        </form>
      )}
      <div className="glass-card" style={{ padding: 20 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
          <div>
            <strong>设备列表</strong>
            {user?.role === 'admin' && <div style={{ color: '#b45309', fontSize: 12, marginTop: 4 }}>测试阶段工具：可手动将机器人恢复为空闲状态。</div>}
          </div>
          <button className="glass-btn glass-btn--outline glass-btn--sm" onClick={load}>刷新状态</button>
        </div>
        {!robots.length ? (
          <div className="empty-state"><p>暂无机器人，请由管理员新增。</p></div>
        ) : (
          <table className="glass-table robot-management-table" style={{ width: '100%' }}>
            <thead>
              <tr>
                <th>设备编号</th>
                <th>设备名称</th>
                <th>当前状态</th>
                {user?.role === 'admin' && <th>管理</th>}
              </tr>
            </thead>
            <tbody>
              {robots.map(robot => {
                const meta = statusMeta[robot.status] || statusMeta.disabled;
                return (
                  <tr key={robot.id}>
                    <td><strong>{robot.code}</strong></td>
                    <td>{robot.name}</td>
                    <td><span className="glass-badge" style={{ color: meta.color, background: meta.background }}>{meta.label}</span></td>
                    {user?.role === 'admin' && (
                      <td>
                        <button className="glass-btn glass-btn--outline glass-btn--sm" onClick={() => { setEditing(robot.id); setForm({ code: robot.code, name: robot.name, status: robot.status }); }}>编辑</button>
                        {robot.status !== 'available' && (
                          <button className="glass-btn glass-btn--outline glass-btn--sm" style={{ marginLeft: 8, color: '#b45309', borderColor: '#f59e0b' }} onClick={() => restoreAvailable(robot)}>测试：恢复为空闲</button>
                        )}
                        <button className="glass-btn glass-btn--danger glass-btn--sm" onClick={() => remove(robot.id)}>删除</button>
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}