import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { createPortal } from 'react-dom';
import * as echarts from 'echarts/core';
import { BarChart, LineChart, PieChart, RadarChart } from 'echarts/charts';
import { GridComponent, LegendComponent, RadarComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsOption } from 'echarts';

echarts.use([BarChart, LineChart, PieChart, RadarChart, GridComponent, LegendComponent, RadarComponent, TooltipComponent, CanvasRenderer]);
import ModuleIcon, { type ModuleIconName } from '../components/ModuleIcon';
import { showToast } from '../components/Toast';
import { auditChainApi, medicineApi, patientApi, prescriptionApi } from '../services/api';
import type { AuditBranchRecord, AuditChainChange, AuditChainRecord, AuditChainVerifyResult } from '../services/api';
import type { Medicine, Prescription } from '../types';
import { STATUS_LABELS } from '../types';
import { formatDateTime } from '../utils/date';

type BasicModuleKind =
  | 'dispense'
  | 'reports'
  | 'medicineSettings'
  | 'writeoff'
  | 'operationLog'
  | 'medicineDown'
  | 'inventory';

interface Props {
  kind: BasicModuleKind;
  title: string;
  icon: ModuleIconName;
}

export default function BasicModulePage({ kind, title, icon }: Props) {
  const [medicines, setMedicines] = useState<Medicine[]>([]);
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [reportPrescriptions, setReportPrescriptions] = useState<Prescription[]>([]);
  const [patientTotal, setPatientTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [keyword, setKeyword] = useState('');
  const [busyId, setBusyId] = useState<number | null>(null);
  const [prefixDrafts, setPrefixDrafts] = useState<Record<number, string>>({});
  const [writeoffIds, setWriteoffIds] = useState<Set<number>>(new Set());
  const [downIds, setDownIds] = useState<Set<number>>(new Set());
  const [auditRecords, setAuditRecords] = useState<AuditChainRecord[]>([]);
  const [auditVerify, setAuditVerify] = useState<AuditChainVerifyResult | null>(null);
  const [auditChanges, setAuditChanges] = useState<AuditChainChange[]>([]);
  const [auditError, setAuditError] = useState('');
  const [auditChecking, setAuditChecking] = useState(false);
  const [auditRevision, setAuditRevision] = useState(0);
  const [auditAction, setAuditAction] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [medicineRes, prescriptionRes, patientRes] = await Promise.all([
        medicineApi.list({ page: 1, pageSize: 200, keyword }),
        prescriptionApi.list({ page: 1, pageSize: 200 }),
        patientApi.list({ page: 1, pageSize: 1 }),
      ]);
      setMedicines(medicineRes.list);
      setPrescriptions(prescriptionRes.list);
      setPatientTotal(patientRes.total);
      setPrefixDrafts(Object.fromEntries(medicineRes.list.map((m) => [m.id, m.trace_code_prefix || ''])));
      if (kind === 'reports') {
        const detailed = await Promise.all(
          prescriptionRes.list.slice(0, 80).map((p) => prescriptionApi.getById(p.id).catch(() => p))
        );
        setReportPrescriptions(detailed);
      }
    } catch (err) {
      console.error(err);
      showToast('数据加载失败', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (kind !== 'operationLog') return;
    let cancelled = false;

    const loadAuditChain = async () => {
      setAuditChecking(true);
      try {
        const [recordRes, verifyRes, inspectRes] = await Promise.all([
          auditChainApi.list({ page: 1, pageSize: 60 }),
          auditChainApi.verify(),
          auditChainApi.inspect(),
        ]);
        if (cancelled) return;
        setAuditRecords(recordRes.list);
        setAuditVerify(verifyRes);
        setAuditChanges(inspectRes.changes);
        setAuditError('');
      } catch (err: any) {
        if (cancelled) return;
        setAuditError(err.response?.data?.error || '审计链校验失败');
      } finally {
        if (!cancelled) setAuditChecking(false);
      }
    };

    loadAuditChain();
    const timer = setInterval(loadAuditChain, 10000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [kind, auditRevision]);

  const runAuditAction = async (name: string, action: () => Promise<unknown>, success: string) => {
    setAuditAction(name);
    try {
      await action();
      showToast(success, 'success');
      setAuditRevision((value) => value + 1);
    } catch (err: any) {
      showToast(err.response?.data?.error || '操作失败', 'error');
    } finally {
      setAuditAction('');
    }
  };

  const filteredMedicines = useMemo(() => {
    const key = keyword.trim().toLowerCase();
    if (!key) return medicines;
    return medicines.filter((m) =>
      [m.name, m.generic_name, m.manufacturer, m.specification].some((v) => String(v || '').toLowerCase().includes(key))
    );
  }, [keyword, medicines]);

  const pendingPrescriptions = prescriptions.filter((p) => p.status === 'pending');
  const approvedPrescriptions = prescriptions.filter((p) => p.status === 'approved');
  const dispensedPrescriptions = prescriptions.filter((p) => p.status === 'dispensed');
  const lowStockMedicines = medicines.filter((m) => Number(m.stock) <= 20);
  const totalStock = medicines.reduce((sum, m) => sum + Number(m.stock || 0), 0);

  const updateMedicine = async (medicine: Medicine, patch: Partial<Medicine>) => {
    setBusyId(medicine.id);
    try {
      await medicineApi.update(medicine.id, {
        name: patch.name ?? medicine.name,
        generic_name: patch.generic_name ?? medicine.generic_name ?? '',
        specification: patch.specification ?? medicine.specification ?? '',
        drug_form: patch.drug_form ?? medicine.drug_form ?? '',
        manufacturer: patch.manufacturer ?? medicine.manufacturer ?? '',
        unit: patch.unit ?? medicine.unit,
        price: patch.price ?? medicine.price,
        stock: patch.stock ?? medicine.stock,
        category: patch.category ?? medicine.category,
        is_narcotic: Boolean(patch.is_narcotic ?? medicine.is_narcotic),
        image_url: patch.image_url ?? medicine.image_url ?? '',
        trace_code_prefix: patch.trace_code_prefix ?? medicine.trace_code_prefix ?? '',
      });
      await load();
      showToast('保存成功', 'success');
    } catch (err: any) {
      showToast(err.response?.data?.error || '保存失败', 'error');
    } finally {
      setBusyId(null);
    }
  };

  const dispense = async (prescription: Prescription) => {
    setBusyId(prescription.id);
    try {
      const res = await prescriptionApi.dispense(prescription.id);
      showToast(res.message || '已确认发药', 'success');
      await load();
    } catch (err: any) {
      showToast(err.response?.data?.error || '发药失败', 'error');
    } finally {
      setBusyId(null);
    }
  };

  const savePrefix = async (medicine: Medicine) => {
    const prefix = (prefixDrafts[medicine.id] || '').trim();
    if (prefix && !/^\d{7}$/.test(prefix)) {
      showToast('前缀必须是 7 位数字', 'error');
      return;
    }
    await updateMedicine(medicine, { trace_code_prefix: prefix });
  };

  const renderContent = () => {
    if (loading) return <div className="loading">加载中...</div>;

    if (kind === 'dispense') {
      return (
        <BasicTable headers={['处方编号', '病人', '诊断', '状态', '时间', '操作']}>
          {approvedPrescriptions.map((p) => (
            <tr key={p.id}>
              <td><strong>{p.prescription_code || `#${p.id}`}</strong></td>
              <td>{p.patient_name || '-'}</td>
              <td>{p.diagnosis}</td>
              <td>{STATUS_LABELS[p.status]}</td>
              <td>{formatDateTime(p.created_at)}</td>
              <td><button className="glass-btn glass-btn--primary glass-btn--sm" disabled={busyId === p.id} onClick={() => dispense(p)}>确认发药</button></td>
            </tr>
          ))}
        </BasicTable>
      );
    }

    if (kind === 'reports') {
      return (
        <ReportDashboard
          patientTotal={patientTotal}
          medicineTotal={medicines.length}
          stockTotal={totalStock}
          lowStockTotal={lowStockMedicines.length}
          pendingTotal={pendingPrescriptions.length}
          approvedTotal={approvedPrescriptions.length}
          dispensedTotal={dispensedPrescriptions.length}
          prescriptions={reportPrescriptions.length > 0 ? reportPrescriptions : prescriptions}
        />
      );
    }

    if (kind === 'medicineSettings') {
      return (
        <BasicTable headers={['药品', '规格', '追溯码前缀', '操作']}>
          {filteredMedicines.map((m) => (
            <tr key={m.id}>
              <td><strong>{m.name}</strong></td>
              <td>{m.specification || '-'}</td>
              <td><input className="glass-input module-basic-input" value={prefixDrafts[m.id] || ''} onChange={(e) => setPrefixDrafts((prev) => ({ ...prev, [m.id]: e.target.value.replace(/\D/g, '').slice(0, 7) }))} placeholder="7位数字" /></td>
              <td><button className="glass-btn glass-btn--primary glass-btn--sm" disabled={busyId === m.id} onClick={() => savePrefix(m)}>保存</button></td>
            </tr>
          ))}
        </BasicTable>
      );
    }

    if (kind === 'writeoff') {
      return (
        <BasicTable headers={['处方编号', '病人', '金额', '状态', '销账']}>
          {dispensedPrescriptions.map((p) => (
            <tr key={p.id}>
              <td><strong>{p.prescription_code || `#${p.id}`}</strong></td>
              <td>{p.patient_name || '-'}</td>
              <td>¥{Number(p.total_amount || 0).toFixed(2)}</td>
              <td>{writeoffIds.has(p.id) ? '已销账' : '待销账'}</td>
              <td><button className="glass-btn glass-btn--primary glass-btn--sm" disabled={writeoffIds.has(p.id)} onClick={() => setWriteoffIds((prev) => new Set(prev).add(p.id))}>确认销账</button></td>
            </tr>
          ))}
        </BasicTable>
      );
    }

    if (kind === 'operationLog') {
      return (
        <AuditChainDashboard
          records={auditRecords}
          verify={auditVerify}
          changes={auditChanges}
          error={auditError}
          checking={auditChecking}
          action={auditAction}
          onAccept={(id) => runAuditAction(`accept-${id}`, () => auditChainApi.accept(id), '新数据链已设为活动链')}
          onReject={(id) => runAuditAction(`reject-${id}`, () => auditChainApi.reject(id), '已取消合并并撤回本机更改')}
        />
      );
    }

    if (kind === 'medicineDown') {
      return (
        <BasicTable headers={['药品', '规格', '库存', '状态', '操作']}>
          {filteredMedicines.map((m) => (
            <tr key={m.id}>
              <td><strong>{m.name}</strong></td>
              <td>{m.specification || '-'}</td>
              <td>{m.stock}</td>
              <td>{downIds.has(m.id) ? '已下架' : '在架'}</td>
              <td><button className="glass-btn glass-btn--danger glass-btn--sm" disabled={downIds.has(m.id)} onClick={() => setDownIds((prev) => new Set(prev).add(m.id))}>下架</button></td>
            </tr>
          ))}
        </BasicTable>
      );
    }

    return (
      <BasicTable headers={['药品', '规格', '厂家', '单位', '库存', '库存状态']}>
        {filteredMedicines.map((m) => (
          <tr key={m.id}>
            <td><strong>{m.name}</strong></td>
            <td>{m.specification || '-'}</td>
            <td>{m.manufacturer || '-'}</td>
            <td>{m.unit}</td>
            <td>{m.stock}</td>
            <td>{Number(m.stock) <= 20 ? '低库存' : '正常'}</td>
          </tr>
        ))}
      </BasicTable>
    );
  };

  const showSearch = ['medicineSettings', 'medicineDown', 'inventory'].includes(kind);

  return (
    <div>
      <motion.div className="page-header flex-between" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div className="page-title-with-icon">
          <span className="page-title-icon"><ModuleIcon name={icon} size={46} /></span>
          <div><h1>{title}</h1><p>{kind === 'operationLog' ? '每 10 秒自动校验链路完整性' : '基础功能已开放'}</p></div>
        </div>
        <div className="page-header-actions">
          {kind === 'operationLog' && <>
            <motion.button
              className={`glass-btn glass-btn--outline glass-btn--sm audit-demo-tamper-btn ${auditAction === 'tamper' ? 'audit-demo-tamper-btn--active' : ''}`}
              disabled={Boolean(auditAction)}
              whileTap={{ scale: .9 }}
              animate={auditAction === 'tamper' ? { scale: [1, .94, 1.04, 1] } : { scale: 1 }}
              transition={{ duration: .55 }}
              onClick={() => runAuditAction('tamper', auditChainApi.demoTamper, '演示数据已修改，正在生成异常分支')}
            >
              {auditAction === 'tamper' ? '修改中…' : '制造数量篡改'}
            </motion.button>
            <button className="glass-btn glass-btn--danger glass-btn--sm" disabled={Boolean(auditAction)} onClick={() => {
              if (window.confirm('仅清空测试区块链和 AI 分析记录，不删除处方业务数据。确定继续吗？')) {
                void runAuditAction('clear', auditChainApi.clear, '测试区块链已清空');
              }
            }}>
              {auditAction === 'clear' ? '清空中…' : '清空测试链'}
            </button>
          </>}
          <button className="glass-btn glass-btn--outline" onClick={kind === 'operationLog' ? () => setAuditRevision((value) => value + 1) : load}>刷新</button>
        </div>
      </motion.div>

      {showSearch && (
        <div className="search-bar">
          <input className="glass-input" placeholder="搜索药品名称、厂家或规格..." value={keyword} onChange={(e) => setKeyword(e.target.value)} />
        </div>
      )}

      <motion.div className={`glass-card module-basic-card ${kind === 'operationLog' ? 'module-basic-card--audit' : ''}`} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}>
        {renderContent()}
      </motion.div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="module-basic-stat">
      <div className="module-basic-stat-value">{value}</div>
      <div className="module-basic-stat-label">{label}</div>
    </div>
  );
}

const AUDIT_EVENT_LABELS: Record<string, string> = {
  PRESCRIPTION_CREATED: '医生开方',
  PHARMACIST_SCAN_CONFIRMED: '药师确认',
  NURSE_SCAN_CONFIRMED: '护士复核',
  PRESCRIPTION_COMPLETED: '处方结束',
  DATA_CHANGED: '数据更改',
  DATA_DELETED: '删除更改',
  DATA_CHANGE_REVERTED: '触发更改撤回',
};

function shortHash(value?: string | null) {
  if (!value) return '-';
  return `${value.slice(0, 8)}...${value.slice(-6)}`;
}

function AuditChainDashboard({
  records,
  verify,
  changes,
  error,
  checking,
  action,
  onAccept,
  onReject,
}: {
  records: AuditChainRecord[];
  verify: AuditChainVerifyResult | null;
  changes: AuditChainChange[];
  error: string;
  checking: boolean;
  action: string;
  onAccept: (id: number) => void;
  onReject: (id: number) => void;
}) {
  const [acceptConfirmOpen, setAcceptConfirmOpen] = useState(false);
  const [rejectConfirmOpen, setRejectConfirmOpen] = useState(false);
  const [differenceFocused, setDifferenceFocused] = useState(false);
  const differenceRef = useRef<HTMLDivElement | null>(null);
  const supportedEvents = new Set(Object.keys(AUDIT_EVENT_LABELS));
  const chronological = [...records].reverse().filter((record) => supportedEvents.has(record.event_type));
  const pendingChanges = changes
    .filter((change) => change.status === 'pending')
    .sort((a, b) => new Date(a.detected_at).getTime() - new Date(b.detected_at).getTime() || a.id - b.id);
  const pendingChange = pendingChanges[0];
  const focusPrescriptionId = String(pendingChange?.prescription_id || chronological[chronological.length - 1]?.entity_id || '');
  const prescriptionRecords = chronological.filter((record) => String(record.entity_id) === focusPrescriptionId);
  const pendingBaselineId = Number(pendingChange?.baseline_record_id || 0);
  const visibleNodes = prescriptionRecords;
  const fallbackBranchRecords: AuditBranchRecord[] = pendingChange ? [
    {
      kind: 'change', source_record_id: null, event_type: pendingChange.change_type === 'deleted' ? 'DATA_DELETED' : 'DATA_CHANGED', entity_id: String(pendingChange.prescription_id),
      event_time: pendingChange.detected_at, payload_hash: pendingChange.new_snapshot_hash,
      previous_hash: pendingChange.old_snapshot_hash, current_hash: pendingChange.new_snapshot_hash,
    },
    {
      kind: 'completion', source_record_id: null, event_type: 'PRESCRIPTION_COMPLETED', entity_id: String(pendingChange.prescription_id),
      event_time: pendingChange.detected_at, payload_hash: pendingChange.new_snapshot_hash,
      previous_hash: pendingChange.new_snapshot_hash, current_hash: pendingChange.new_snapshot_hash,
    },
  ] : [];
  const candidateBranchRecords = pendingChange?.branch_records?.length ? pendingChange.branch_records : fallbackBranchRecords;
  const isChainBroken = Boolean(verify && !verify.valid);
  const hasDataChange = Boolean(pendingChange);
  const latest = chronological[chronological.length - 1];
  const acceptedChangeForRecord = (record: AuditChainRecord) =>
    ['DATA_CHANGED', 'DATA_DELETED'].includes(record.event_type)
      ? changes.find((change) => change.status === 'accepted' && change.id === Number(record.change_id))
      : undefined;

  const locateDifference = () => {
    differenceRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setDifferenceFocused(true);
    window.setTimeout(() => setDifferenceFocused(false), 1600);
  };

  useEffect(() => {
    if (!pendingChange) return undefined;
    const handleShortcut = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.matches('input, textarea, select, [contenteditable="true"]')) return;
      if (event.key.toLowerCase() === 'd') {
        event.preventDefault();
        locateDifference();
      }
      if (event.key === 'Escape') {
        setAcceptConfirmOpen(false);
        setRejectConfirmOpen(false);
      }
    };
    window.addEventListener('keydown', handleShortcut);
    return () => window.removeEventListener('keydown', handleShortcut);
  }, [pendingChange]);

  const renderAnalysis = (change: AuditChainChange) => (
    <aside className="audit-node-analysis">
      <div className="audit-node-analysis-head">
        <strong>AI 分析</strong>
        <span>{change.ai_status === 'completed' ? 'DeepSeek' : change.ai_status === 'rules_fallback' ? '本地规则' : change.ai_status === 'running' ? '分析中' : '待分析'}</span>
      </div>
      <div className="audit-node-actor">{change.actor_name || '未知操作人'} · {change.actor_source}</div>
      <pre>{change.ai_analysis || '正在分析字段差异与修改意图…'}</pre>
    </aside>
  );

  return (
    <div className="audit-chain-shell">
      <div className={`audit-chain-status ${isChainBroken || hasDataChange ? 'audit-chain-status--broken' : ''}`}>
        <div className="audit-chain-status-copy">
          <span className="audit-chain-kicker">区块链完整性</span>
          <h3>{isChainBroken ? '区块哈希已损坏' : hasDataChange ? '检测到处方数据与链上快照不一致' : '活动链与处方数据库一致'}</h3>
          {hasDataChange && <button className="audit-locate-difference" type="button" onClick={locateDifference} title="快捷键 D">
            快速定位差异 <kbd>D</kbd>
          </button>}
          {error && <p>{error}</p>}
        </div>
        <div className={`audit-chain-proof-grid ${hasDataChange ? '' : 'audit-chain-proof-grid--compact'}`}>
          <div className="audit-chain-proof">
            <span>{checking ? '校验中' : '链上节点'}</span>
            <strong>{visibleNodes.length}</strong>
          </div>
          {hasDataChange && <div className="audit-chain-proof"><span>是否需要同步</span><strong>是</strong></div>}
          <div className="audit-chain-proof audit-chain-proof--hash">
            <span>链尾指纹</span>
            <code>{shortHash(verify?.last_hash || latest?.current_hash)}</code>
          </div>
        </div>
      </div>

      <div className={`audit-branch-grid ${hasDataChange ? 'audit-branch-grid--diff' : 'audit-branch-grid--single'}`}>
        <section className="audit-chain-panel audit-chain-panel--active">
          {hasDataChange && <div className="audit-chain-panel-head"><h4>当前基线</h4></div>}
          <div className="audit-chain-visual audit-chain-visual--vertical" aria-label="已确认活动链" tabIndex={0}>
            {visibleNodes.length === 0 ? <div className="audit-chain-empty">暂无存证</div> : visibleNodes.map((record, index) => {
              const acceptedChange = acceptedChangeForRecord(record);
              return (
                <div className={`audit-chain-node-row ${acceptedChange ? 'audit-chain-node-row--analysis' : ''}`} key={record.id}>
                  <div className={`audit-chain-node ${record.event_type === 'DATA_CHANGED' ? 'audit-chain-node--changed' : record.event_type === 'DATA_DELETED' ? 'audit-chain-node--deleted' : ''} ${hasDataChange && record.id === pendingBaselineId ? 'audit-chain-node--baseline-alert' : ''} ${differenceFocused && record.id === pendingBaselineId ? 'audit-chain-node--difference-focus' : ''}`}>
                    <div className="audit-chain-node-index">节点 {index + 1}</div>
                    {hasDataChange && record.id === pendingBaselineId && <div className="audit-chain-node-alert">原记录已与数据库数据偏离</div>}
                    <div className="audit-chain-node-title">{AUDIT_EVENT_LABELS[record.event_type]}</div>
                    <div className="audit-chain-node-time">{formatDateTime(record.event_time)}</div>
                    <div className="audit-chain-node-hash"><span>HASH</span>{shortHash(record.current_hash)}</div>
                    {index < visibleNodes.length - 1 && <span className="audit-chain-link" />}
                  </div>
                  {acceptedChange && renderAnalysis(acceptedChange)}
                </div>
              );
            })}
            {hasDataChange && visibleNodes.length > 0 && <div className="audit-chain-node-row audit-chain-node-row--spacer" aria-hidden="true" />}
          </div>
        </section>

        {hasDataChange && <div className="audit-branch-switch-slot" aria-hidden="true" />}

        {pendingChange && <motion.section
          key={pendingChange.id}
          className="audit-chain-panel audit-chain-panel--candidate"
          initial={{ opacity: 0, x: 34, scale: .96 }}
          animate={{ opacity: 1, x: 0, scale: 1 }}
          transition={{ type: 'spring', stiffness: 210, damping: 17, mass: .85 }}
        >
          <div className="audit-chain-panel-head">
            <h4>差异分支</h4>
            <small>{formatDateTime(pendingChange.detected_at)}</small>
          </div>
          <div className="audit-chain-visual audit-chain-visual--vertical audit-chain-visual--candidate">
            {candidateBranchRecords.map((record, index) => {
              const isChangeNode = record.kind === 'change';
              const isCompletionNode = record.kind === 'completion';
              const isLatestNode = index === candidateBranchRecords.length - 1;
              return <div ref={isChangeNode ? differenceRef : undefined} className={`audit-chain-node-row ${isChangeNode ? 'audit-chain-node-row--analysis' : ''}`} key={`${record.kind}-${record.source_record_id ?? index}`}>
                {isChangeNode && <motion.span className="audit-change-bridge" aria-hidden="true" initial={{ opacity: 0, scale: .82 }} animate={{ opacity: 1, scale: 1 }} transition={{ type: 'spring', stiffness: 280, damping: 20 }}>→</motion.span>}
                <div className={`audit-chain-node ${isChangeNode ? (record.event_type === 'DATA_DELETED' ? 'audit-chain-node--deleted' : 'audit-chain-node--changed') : isCompletionNode ? 'audit-chain-node--candidate' : ''} ${differenceFocused && isChangeNode ? 'audit-chain-node--difference-focus' : ''}`}>
                  <div className="audit-chain-node-index">节点 {visibleNodes.length + index + 1}{isLatestNode ? ' · 最新' : ''}</div>
                  <div className="audit-chain-node-title">{isChangeNode ? (record.event_type === 'DATA_DELETED' ? '删除更改' : '数据更改') : isCompletionNode ? '处方结束 · 新链' : AUDIT_EVENT_LABELS[record.event_type]}</div>
                  <div className="audit-chain-node-time">{formatDateTime(record.event_time)}</div>
                  <div className="audit-chain-node-hash"><span>{isChangeNode ? 'NEW' : 'HASH'}</span>{shortHash(record.current_hash)}</div>
                  {index < candidateBranchRecords.length - 1 && <span className="audit-chain-link" />}
                </div>
                {isChangeNode && renderAnalysis(pendingChange)}
              </div>;
            })}
          </div>
          <div className="audit-sync-action">
            <button className="glass-btn audit-accept-btn" disabled={Boolean(action)} onClick={() => setAcceptConfirmOpen(true)}>
              {action === `accept-${pendingChange.id}` ? '更新中…' : '同步差异分支'}
            </button>
            <button className="glass-btn glass-btn--outline audit-reject-btn" disabled={Boolean(action)} onClick={() => setRejectConfirmOpen(true)}>
              {action === `reject-${pendingChange.id}` ? '撤回中…' : '不合并节点'}
            </button>
          </div>
        </motion.section>}
      </div>

      {createPortal(<AnimatePresence>
        {pendingChange && acceptConfirmOpen && (
          <motion.div className="confirm-overlay audit-confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setAcceptConfirmOpen(false)}>
            <motion.div className="confirm-dialog glass-card audit-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="audit-confirm-title" initial={{ opacity: 0, y: 18, scale: .96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: .97 }} transition={{ type: 'spring', stiffness: 300, damping: 24 }} onClick={(event) => event.stopPropagation()}>
              <div className="audit-confirm-icon">⇄</div>
              <h3 id="audit-confirm-title">同步差异分支</h3>
              <p>将右侧分支设为新的活动链，并保留原链用于追责。</p>
              <div className="audit-confirm-summary">
                <span>待同步处方</span>
                <strong>#{pendingChange.prescription_id}</strong>
                <span>处理结果</span>
                <strong>生成新链并更新基线</strong>
              </div>
              <div className="confirm-actions">
                <motion.button className="glass-btn glass-btn--primary" disabled={Boolean(action)} whileTap={{ scale: .97 }} onClick={() => { setAcceptConfirmOpen(false); onAccept(pendingChange.id); }}>确认同步</motion.button>
                <button className="glass-btn glass-btn--outline" disabled={Boolean(action)} onClick={() => setAcceptConfirmOpen(false)}>取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>, document.body)}

      {createPortal(<AnimatePresence>
        {pendingChange && rejectConfirmOpen && (
          <motion.div className="confirm-overlay audit-confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setRejectConfirmOpen(false)}>
            <motion.div className="confirm-dialog glass-card audit-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="audit-reject-confirm-title" initial={{ opacity: 0, y: 18, scale: .96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: .97 }} transition={{ type: 'spring', stiffness: 300, damping: 24 }} onClick={(event) => event.stopPropagation()}>
              <div className="audit-confirm-icon">↶</div>
              <h3 id="audit-reject-confirm-title">确认不合并节点？</h3>
              <p>将放弃右侧差异分支，恢复删除前的处方或修改前的药品数量，并在活动链记录一次“触发更改撤回”。</p>
              <div className="audit-confirm-summary">
                <span>待撤回处方</span>
                <strong>#{pendingChange.prescription_id}</strong>
                <span>处理结果</span>
                <strong>恢复本机数据并关闭差异分支</strong>
              </div>
              <div className="confirm-actions">
                <motion.button className="glass-btn glass-btn--primary" disabled={Boolean(action)} whileTap={{ scale: .97 }} onClick={() => { setRejectConfirmOpen(false); onReject(pendingChange.id); }}>确认撤回</motion.button>
                <button className="glass-btn glass-btn--outline" disabled={Boolean(action)} onClick={() => setRejectConfirmOpen(false)}>取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>, document.body)}
    </div>
  );
}
function ReportDashboard({
  patientTotal,
  medicineTotal,
  stockTotal,
  lowStockTotal,
  pendingTotal,
  approvedTotal,
  dispensedTotal,
  prescriptions,
}: {
  patientTotal: number;
  medicineTotal: number;
  stockTotal: number;
  lowStockTotal: number;
  pendingTotal: number;
  approvedTotal: number;
  dispensedTotal: number;
  prescriptions: Prescription[];
}) {
  const patientCounts = topEntries(countBy(prescriptions, (p) => p.patient_name || '病人#' + p.patient_id), 8);
  const diagnosisCounts = topEntries(countBy(prescriptions, (p) => p.diagnosis || '未填写诊断'), 6);
  const medicineUsage = topEntries(sumMedicineUsage(prescriptions), 8);
  const trend = buildPrescriptionTrend(prescriptions);

  return (
    <>
      <div className="module-basic-stats report-stats">
        <Stat label="病人总数" value={patientTotal} />
        <Stat label="药品种类" value={medicineTotal} />
        <Stat label="库存总量" value={stockTotal} />
        <Stat label="低库存药品" value={lowStockTotal} />
      </div>
      <div className="report-status-strip">
        <span>待审核 {pendingTotal}</span>
        <span>待发药 {approvedTotal}</span>
        <span>已发药 {dispensedTotal}</span>
        <span>统计处方 {prescriptions.length}</span>
      </div>
      <div className="report-chart-grid">
        <ChartPanel
          title="病人处方次数"
          note="按病人汇总处方数量"
          option={{
            tooltip: { trigger: 'axis' },
            grid: { left: 38, right: 18, top: 28, bottom: 56 },
            xAxis: { type: 'category', data: patientCounts.map(([name]) => name), axisLabel: { rotate: 28 } },
            yAxis: { type: 'value', minInterval: 1 },
            series: [{
              type: 'bar',
              data: patientCounts.map(([, value]) => value),
              barMaxWidth: 34,
              itemStyle: { color: '#3178C6', borderRadius: [8, 8, 2, 2] },
            }],
          }}
        />
        <ChartPanel
          title="药品消耗数量"
          note="按处方明细数量汇总"
          option={{
            tooltip: { trigger: 'item' },
            legend: { bottom: 0, type: 'scroll' },
            series: [{
              type: 'pie',
              radius: ['42%', '70%'],
              center: ['50%', '45%'],
              data: medicineUsage.map(([name, value]) => ({ name, value })),
              itemStyle: { borderColor: '#fff', borderWidth: 3 },
            }],
          }}
        />
        <ChartPanel
          title="疾病诊断分布"
          note="雷达图展示高频诊断"
          option={{
            tooltip: {},
            radar: {
              radius: '66%',
              indicator: diagnosisCounts.map(([name, value]) => ({ name, max: Math.max(value, 1) + 1 })),
              splitArea: { areaStyle: { color: ['rgba(49,120,198,0.04)', 'rgba(50,198,186,0.08)'] } },
            },
            series: [{
              type: 'radar',
              data: [{ value: diagnosisCounts.map(([, value]) => value), name: '诊断次数' }],
              areaStyle: { color: 'rgba(50,198,186,0.22)' },
              lineStyle: { color: '#32C6BA', width: 3 },
              itemStyle: { color: '#32C6BA' },
            }],
          }}
        />
        <ChartPanel
          title="处方开具趋势"
          note="按日期统计处方数量"
          option={{
            tooltip: { trigger: 'axis' },
            grid: { left: 38, right: 18, top: 28, bottom: 40 },
            xAxis: { type: 'category', data: trend.map(([date]) => date) },
            yAxis: { type: 'value', minInterval: 1 },
            series: [{
              type: 'line',
              smooth: true,
              data: trend.map(([, value]) => value),
              symbolSize: 8,
              lineStyle: { color: '#E78CA8', width: 3 },
              itemStyle: { color: '#E78CA8' },
              areaStyle: { color: 'rgba(231,140,168,0.18)' },
            }],
          }}
        />
      </div>
    </>
  );
}

function ChartPanel({ title, note, option }: { title: string; note: string; option: EChartsOption }) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption(option);
    const resize = () => chart.resize();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      chart.dispose();
    };
  }, [option]);

  return (
    <div className="report-chart-panel">
      <div className="report-chart-head">
        <h3>{title}</h3>
        <span>{note}</span>
      </div>
      <div ref={ref} className="report-chart" />
    </div>
  );
}

function countBy(items: Prescription[], getKey: (item: Prescription) => string) {
  const result = new Map<string, number>();
  for (const item of items) {
    const key = getKey(item).trim() || '未填写';
    result.set(key, (result.get(key) || 0) + 1);
  }
  return result;
}

function sumMedicineUsage(prescriptions: Prescription[]) {
  const result = new Map<string, number>();
  for (const prescription of prescriptions) {
    for (const item of prescription.items || []) {
      const key = item.medicine_name || '药品#' + item.medicine_id;
      result.set(key, (result.get(key) || 0) + Number(item.quantity || 1));
    }
  }
  if (result.size === 0) {
    result.set('暂无明细', 0);
  }
  return result;
}

function buildPrescriptionTrend(prescriptions: Prescription[]) {
  return topEntries(countBy(prescriptions, (p) => formatDateTime(p.created_at).slice(0, 10)), 10).sort(([a], [b]) => a.localeCompare(b));
}

function topEntries(map: Map<string, number>, limit: number): Array<[string, number]> {
  const entries = Array.from(map.entries()).sort((a, b) => b[1] - a[1]).slice(0, limit);
  return entries.length > 0 ? entries : [['暂无数据', 0]];
}

function BasicTable({ headers, children }: { headers: string[]; children: React.ReactNode }) {
  return (
    <table className="glass-table module-basic-table">
      <thead>
        <tr>{headers.map((h) => <th key={h}>{h}</th>)}</tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}
