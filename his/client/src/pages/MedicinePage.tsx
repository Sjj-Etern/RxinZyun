import React, { useState, useEffect, useRef, FormEvent } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { medicineApi, medicineTraceCodeApi } from '../services/api';
import type { Medicine, MedicineFormData, MedicineTraceCode } from '../types';
import { TRACE_STATUS_LABELS, TRACE_STATUS_COLORS } from '../types';
import Modal from '../components/Modal';
import { showToast } from '../components/Toast';
import ModuleIcon from '../components/ModuleIcon';
import GlassSelect from '../components/GlassSelect';
import { formatDateTime } from '../utils/date';

const emptyForm: MedicineFormData = { name: '', generic_name: '', specification: '', drug_form: '', manufacturer: '', unit: '盒', price: '', stock: '', category: '处方药', is_narcotic: false, image_url: '', trace_code_prefix: '' };
const DRUG_FORM_OPTIONS = [
  { value: '', label: '请选择' },
  { value: '片剂', label: '片剂' },
  { value: '胶囊剂', label: '胶囊剂' },
  { value: '注射剂', label: '注射剂' },
  { value: '口服液', label: '口服液' },
  { value: '颗粒剂', label: '颗粒剂' },
  { value: '外用', label: '外用' },
];
const MEDICINE_CATEGORY_OPTIONS = [
  { value: '处方药', label: '处方药' },
  { value: '非处方药', label: '非处方药' },
];
const NARCOTIC_OPTIONS = [
  { value: '0', label: '否' },
  { value: '1', label: '是' },
];

const rowAnim = {
  hidden: { opacity: 0, y: 10 },
  visible: (i: number) => ({ opacity: 1, y: 0, transition: { delay: i * 0.04 } }),
};

export default function MedicinePage() {
  const [medicines, setMedicines] = useState<Medicine[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<MedicineFormData>(emptyForm);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Medicine | null>(null);
  const [expandedMedicineId, setExpandedMedicineId] = useState<number | null>(null);
  const [traceCodes, setTraceCodes] = useState<MedicineTraceCode[]>([]);
  const [traceTotal, setTraceTotal] = useState(0);
  const [traceCodeLoading, setTraceCodeLoading] = useState(false);
  const [traceCodePage, setTraceCodePage] = useState(1);
  const [newTraceCode, setNewTraceCode] = useState('');
  const [traceError, setTraceError] = useState('');
  const [traceConfirm, setTraceConfirm] = useState<{ type: string; tcId: number; label: string } | null>(null);
  const [busyIds, setBusyIds] = useState<Set<number>>(new Set());
  const timersRef = useRef<Record<number, ReturnType<typeof setTimeout>>>({});
  // 轮询刷新用 refs（避免闭包过期问题）
  const loadTraceCodesRef = useRef<typeof loadTraceCodes>(null as any);
  const expandedMedicineIdRef = useRef<number | null>(null);
  const traceCodePageRef = useRef(1);
  const pageSize = 10;
  const tracePageSize = 15;

  const loadList = async (p: number, kw: string) => {
    setLoading(true);
    try {
      const data = await medicineApi.list({ page: p, pageSize, keyword: kw });
      setMedicines(data.list);
      setTotal(data.total);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadList(page, keyword); }, [page, keyword]);

  const totalPages = Math.ceil(total / pageSize);

  const openNew = () => { setEditId(null); setForm(emptyForm); setError(''); setModalOpen(true); };

  const openEdit = (m: Medicine) => {
    setEditId(m.id);
    setForm({ name: m.name, generic_name: m.generic_name || '', specification: m.specification || '', drug_form: m.drug_form || '', manufacturer: m.manufacturer || '', unit: m.unit, price: m.price, stock: m.stock, category: m.category || '处方药', is_narcotic: !!m.is_narcotic, image_url: m.image_url || '', trace_code_prefix: m.trace_code_prefix || '' });
    setError('');
    setModalOpen(true);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.name) { setError('药品名称为必填项'); return; }
    setSubmitting(true); setError('');
    try {
      if (editId) {
        await medicineApi.update(editId, form);
      } else {
        await medicineApi.create(form);
      }
      setModalOpen(false);
      loadList(page, keyword);
    } catch (err: any) { setError(err.response?.data?.error || '保存失败'); }
    finally { setSubmitting(false); }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    try {
      await medicineApi.delete(confirmDelete.id);
      setConfirmDelete(null);
      loadList(page, keyword);
    } catch (err: any) { showToast(err.response?.data?.error || '删除失败', 'error'); }
  };

  const loadTraceCodes = async (medicineId: number, page: number, silent = false) => {
    if (!silent) setTraceCodeLoading(true);
    try {
      const data = await medicineTraceCodeApi.list({ medicine_id: medicineId, page, pageSize: tracePageSize });
      setTraceCodes(data.list);
      setTraceTotal(data.total);
    } catch (err) { console.error(err); }
    finally { if (!silent) setTraceCodeLoading(false); }
  };

  const toggleExpand = async (medicineId: number) => {
    if (expandedMedicineId === medicineId) {
      setExpandedMedicineId(null);
      setTraceCodes([]);
    } else {
      setExpandedMedicineId(medicineId);
      setTraceCodePage(1);
      setTraceError('');
      await loadTraceCodes(medicineId, 1);
    }
  };

  const handleAddTraceCode = async (medicineId: number) => {
    if (!newTraceCode.trim()) { setTraceError('请输入追溯码'); return; }
    setTraceError('');
    try {
      await medicineTraceCodeApi.create({ medicine_id: medicineId, trace_code: newTraceCode.trim() });
      setNewTraceCode('');
      setTraceCodePage(1);
      await loadTraceCodes(medicineId, 1);
    } catch (err: any) { setTraceError(err.response?.data?.error || '添加失败'); }
  };

  const isBusy = (tcId: number) => busyIds.has(tcId);

  const lockId = (tcId: number) => {
    setBusyIds(prev => new Set(prev).add(tcId));
    if (timersRef.current[tcId]) clearTimeout(timersRef.current[tcId]);
    timersRef.current[tcId] = setTimeout(() => {
      setBusyIds(prev => { const next = new Set(prev); next.delete(tcId); return next; });
      delete timersRef.current[tcId];
    }, 3000);
  };

  const handleScan = async (tcId: number) => {
    if (isBusy(tcId)) return;
    lockId(tcId);
    try {
      await medicineTraceCodeApi.scan(tcId);
      // 扫描后重新加载列表，让被扫的追溯码排到开头
      if (expandedMedicineId) {
        setTraceCodePage(1);
        await loadTraceCodes(expandedMedicineId, 1);
      }
    } catch (err: any) { showToast(err.response?.data?.error || '扫描操作失败', 'error'); }
  };

  const handleUnscan = async (tcId: number) => {
    if (isBusy(tcId)) return;
    lockId(tcId);
    try {
      await medicineTraceCodeApi.unscan(tcId);
      // 撤回后重新加载列表，更新排序
      if (expandedMedicineId) {
        setTraceCodePage(1);
        await loadTraceCodes(expandedMedicineId, 1);
      }
    } catch (err: any) { showToast(err.response?.data?.error || '撤回失败', 'error'); }
  };

  const handleDeleteTraceCode = async (tcId: number) => {
    if (isBusy(tcId)) return;
    lockId(tcId);
    try {
      await medicineTraceCodeApi.delete(tcId);
      // 删除后重新加载列表
      if (expandedMedicineId) {
        setTraceCodePage(1);
        await loadTraceCodes(expandedMedicineId, 1);
      }
    } catch (err: any) { showToast(err.response?.data?.error || '删除失败', 'error'); }
  };

  const handleTraceConfirm = async () => {
    if (!traceConfirm) return;
    const { type, tcId } = traceConfirm;
    setTraceConfirm(null);
    if (type === 'scan') await handleScan(tcId);
    else if (type === 'unscan') await handleUnscan(tcId);
    else if (type === 'delete') await handleDeleteTraceCode(tcId);
  };

  // 保持 refs 与最新状态同步（供轮询使用）
  loadTraceCodesRef.current = loadTraceCodes;
  expandedMedicineIdRef.current = expandedMedicineId;
  traceCodePageRef.current = traceCodePage;

  // 追溯码自动刷新轮询：展开时每3秒轮询一次，手机扫码后桌面端立即显示
  useEffect(() => {
    if (expandedMedicineId === null) return;
    const interval = setInterval(() => {
      const mid = expandedMedicineIdRef.current;
      if (mid !== null) {
        loadTraceCodesRef.current(mid, traceCodePageRef.current, true);
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [expandedMedicineId]);

  return (
    <div>
      <motion.div className="page-header flex-between" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div>
          <h1>药品管理</h1>
          <p>管理药品库存信息</p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <motion.button className="glass-btn glass-btn--outline" style={{ color: 'var(--red)', borderColor: 'var(--red)' }} onClick={async () => {
            if (!confirm('确定要删除全部追溯码并重新生成吗？\n\n此操作不可撤销，将根据每种药品的库存数量和固定前缀重新生成追溯码。')) return;
            try {
              const res = await medicineTraceCodeApi.regenerateAll();
              showToast(res.message, 'success');
              loadList(page, keyword);
              if (expandedMedicineId) {
                setTraceCodePage(1);
                loadTraceCodes(expandedMedicineId, 1);
              }
            } catch (err: any) { showToast(err.response?.data?.error || '操作失败', 'error'); }
          }} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
            清空重新生成
          </motion.button>
          <motion.button className="glass-btn glass-btn--primary" onClick={openNew} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>
            ＋ 新增药品
          </motion.button>
        </div>
      </motion.div>

      <motion.div className="search-bar" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
        <input className="glass-input" placeholder="搜索药品名称或厂家..." value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (setPage(1), loadList(1, keyword))} />
        <button className="glass-btn glass-btn--primary" onClick={() => { setPage(1); loadList(1, keyword); }}>搜索</button>
      </motion.div>

      {/* Form Modal */}
      <Modal isOpen={modalOpen} onClose={() => setModalOpen(false)} title={editId ? '编辑药品' : '新增药品'}>
        {error && <div className="alert alert--error">{error}</div>}
        <form onSubmit={handleSubmit}>
          <div className="form-grid">
            <div className="form-group">
              <label>药品名称（商品名）*</label>
              <input className="glass-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="请输入药品商品名" />
            </div>
            <div className="form-group">
              <label>通用名 (CADN)</label>
              <input className="glass-input" value={form.generic_name} onChange={(e) => setForm({ ...form, generic_name: e.target.value })} placeholder="药品通用名" />
            </div>
            <div className="form-group">
              <label>剂型</label>
              <GlassSelect value={form.drug_form} options={DRUG_FORM_OPTIONS} onChange={(drug_form) => setForm({ ...form, drug_form })} />
            </div>
            <div className="form-group">
              <label>规格</label>
              <input className="glass-input" value={form.specification} onChange={(e) => setForm({ ...form, specification: e.target.value })} placeholder="如 0.5g×24粒" />
            </div>
            <div className="form-group">
              <label>生产厂家</label>
              <input className="glass-input" value={form.manufacturer} onChange={(e) => setForm({ ...form, manufacturer: e.target.value })} placeholder="请输入生产厂家" />
            </div>
            <div className="form-group">
              <label>单位</label>
              <input className="glass-input" value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} placeholder="盒/瓶/支" />
            </div>
            <div className="form-group">
              <label>单价 (元)</label>
              <input className="glass-input" type="number" step="0.01" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value === '' ? '' : Number(e.target.value) })} placeholder="0.00" />
            </div>
            <div className="form-group">
              <label>库存</label>
              <input className="glass-input" type="number" value={form.stock} onChange={(e) => setForm({ ...form, stock: e.target.value === '' ? '' : Number(e.target.value) })} placeholder="0" />
            </div>
            <div className="form-group">
              <label>药品分类</label>
              <GlassSelect value={form.category} options={MEDICINE_CATEGORY_OPTIONS} onChange={(category) => setForm({ ...form, category })} />
            </div>
            <div className="form-group">
              <label>麻醉/精神药品</label>
              <GlassSelect value={form.is_narcotic ? '1' : '0'} options={NARCOTIC_OPTIONS} onChange={(value) => setForm({ ...form, is_narcotic: value === '1' })} />
            </div>
            <div className="form-group form-group--full">
              <label>图片URL</label>
              <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
                <input className="glass-input" style={{ flex: 1 }} value={form.image_url} onChange={(e) => setForm({ ...form, image_url: e.target.value })} placeholder="输入图片链接地址" />
                {form.image_url && (
                  <img src={form.image_url} alt="预览" style={{ width: 48, height: 48, borderRadius: 8, objectFit: 'cover', border: '1px solid var(--glass-border)' }} />
                )}
              </div>
            </div>
            <div className="form-group">
              <label>追溯码前缀（7位数字）</label>
              <input className="glass-input" value={form.trace_code_prefix} onChange={(e) => setForm({ ...form, trace_code_prefix: e.target.value.replace(/\D/g, '').slice(0, 7) })} placeholder="如 1730604" maxLength={7} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 20 }}>
            <motion.button className="glass-btn glass-btn--primary" type="submit" disabled={submitting} whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              {submitting ? '保存中...' : '保存'}
            </motion.button>
            <button className="glass-btn glass-btn--outline" type="button" onClick={() => setModalOpen(false)}>取消</button>
          </div>
        </form>
      </Modal>

      {/* Table */}
      <motion.div className="glass-card" style={{ padding: 20 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}>
        {loading ? (
          <div className="loading">加载中...</div>
        ) : medicines.length === 0 ? (
          <div className="empty-state"><div className="empty-icon"><ModuleIcon name="medicines" size={48} /></div><p>暂无药品数据</p></div>
        ) : (
          <>
            <table className="glass-table medicine-table">
              <thead>
                <tr><th>追溯码</th><th>药品名称</th><th>规格</th><th>厂家</th><th>单位</th><th>单价</th><th>库存</th><th>操作</th></tr>
              </thead>
              <tbody>
                <AnimatePresence>
                  {medicines.map((m, i) => (
                    <React.Fragment key={m.id}>
                      <motion.tr variants={rowAnim} custom={i} initial="hidden" animate="visible" exit={{ opacity: 0 }}>
                      <td>
                        <button className="expand-btn" onClick={() => toggleExpand(m.id)}>
                          {expandedMedicineId === m.id ? '收起' : '展开'}
                        </button>
                      </td>
                      <td>
                        <strong>{m.name}</strong>
                        {m.trace_code_prefix && (
                          <span style={{ marginLeft: 8, fontSize: 12, color: 'var(--blue)', background: 'rgba(74,144,217,0.1)', padding: '2px 6px', borderRadius: 4 }}>
                            {m.trace_code_prefix}
                          </span>
                        )}
                      </td>
                      <td>{m.specification || '-'}</td>
                      <td>{m.manufacturer || '-'}</td>
                      <td>{m.unit}</td>
                      <td style={{ color: 'var(--blue)', fontWeight: 600 }}>¥{Number(m.price).toFixed(2)}</td>
                      <td>{m.stock}</td>
                      <td>
                        <div className="action-btns">
                          <motion.button className="glass-btn glass-btn--outline glass-btn--sm" onClick={() => openEdit(m)} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>编辑</motion.button>
                          <motion.button className="glass-btn glass-btn--danger glass-btn--sm" onClick={() => setConfirmDelete(m)} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>删除</motion.button>
                        </div>
                      </td>
                    </motion.tr>
                    {expandedMedicineId === m.id && (
                      <tr className="trace-sub-row">
                        <td colSpan={8}>
                          <div className="trace-sub-panel">
                            <div className="trace-sub-header">
                              <h4>追溯码 — {m.name}（共 {traceTotal} 条）{m.trace_code_prefix && <span style={{ fontSize: 12, color: 'var(--blue)', background: 'rgba(74,144,217,0.1)', padding: '2px 8px', borderRadius: 4, marginLeft: 8 }}>前缀: {m.trace_code_prefix}</span>}</h4>
                            </div>
                            <div className="trace-add-form" style={{ marginBottom: 14 }}>
                              <input className="glass-input" style={{ flex: 1, maxWidth: 320 }} placeholder="输入追溯码..." value={newTraceCode} onChange={(e) => setNewTraceCode(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') handleAddTraceCode(m.id); }} />
                              <motion.button className="glass-btn glass-btn--primary glass-btn--sm" onClick={() => handleAddTraceCode(m.id)} whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>添加</motion.button>
                            </div>
                            {traceError && <div className="alert--error">{traceError}</div>}
                            {traceCodeLoading ? (
                              <div className="loading">加载追溯码...</div>
                            ) : traceCodes.length === 0 ? (
                              <div className="empty-state"><p>暂无追溯码，请输入后自动生成</p></div>
                            ) : (
                              <>
                                <table className="trace-sub-table">
                                  <thead>
                                    <tr>
                                      <th style={{ width: '20%' }}>追溯码</th>
                                      <th style={{ width: '8%' }}>状态</th>
                                      <th style={{ width: '14%', textAlign: 'center' }}>识别时间</th>
                                      <th style={{ width: '14%', textAlign: 'center' }}>出库时间</th>
                                      <th style={{ width: '14%', textAlign: 'center' }}>确认时间</th>
                                      <th style={{ width: '22%', textAlign: 'center' }}>操作</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {traceCodes.map((tc, idx) => (
                                      <tr key={tc.id}>
                                        <td>
                                          <code style={{ fontSize: 11, background: 'rgba(0,0,0,0.04)', padding: '2px 6px', borderRadius: 4, wordBreak: 'break-all' }}>
                                            {tc.trace_code}
                                          </code>
                                        </td>
                                        <td>
                                          <span className="glass-badge" style={{ background: TRACE_STATUS_COLORS[tc.status] + '20', color: TRACE_STATUS_COLORS[tc.status], fontSize: 11 }}>
                                            {TRACE_STATUS_LABELS[tc.status]}
                                          </span>
                                        </td>
                                        <td style={{ fontSize: 12, textAlign: 'center' }}>{formatDateTime(tc.scan1_time)}</td>
                                        <td style={{ fontSize: 12, textAlign: 'center' }}>{formatDateTime(tc.scan2_time)}</td>
                                        <td style={{ fontSize: 12, textAlign: 'center' }}>{formatDateTime(tc.scan3_time)}</td>
                                        <td style={{ textAlign: 'center' }}>
                                          <div className="action-btns" style={{ flexWrap: 'nowrap', justifyContent: 'center' }}>
                                            <motion.button className="glass-btn glass-btn--outline glass-btn--xs" onClick={() => setTraceConfirm({ type: 'scan', tcId: tc.id, label: tc.status === 'pending' ? '出库' : '确认' })} disabled={tc.status === 'scanned_confirm' || isBusy(tc.id)} whileHover={tc.status === 'scanned_confirm' || isBusy(tc.id) ? {} : { scale: 1.05 }} whileTap={tc.status === 'scanned_confirm' || isBusy(tc.id) ? {} : { scale: 0.95 }}>
                                              {tc.status === 'pending' ? '出库' : tc.status === 'scanned_outbound' ? '确认' : '完成'}
                                            </motion.button>
                                            {tc.status !== 'pending' && (
                                              <motion.button className="glass-btn glass-btn--success glass-btn--xs" onClick={() => setTraceConfirm({ type: 'unscan', tcId: tc.id, label: '撤回' })} disabled={isBusy(tc.id)} whileHover={isBusy(tc.id) ? {} : { scale: 1.05 }} whileTap={isBusy(tc.id) ? {} : { scale: 0.95 }}>撤回</motion.button>
                                            )}
                                            <motion.button className="glass-btn glass-btn--danger glass-btn--xs" onClick={() => setTraceConfirm({ type: 'delete', tcId: tc.id, label: '删除' })} disabled={isBusy(tc.id)} whileHover={isBusy(tc.id) ? {} : { scale: 1.05 }} whileTap={isBusy(tc.id) ? {} : { scale: 0.95 }}>删除</motion.button>
                                          </div>
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                                {traceTotal > tracePageSize && (
                                  <div className="pagination" style={{ marginTop: 10 }}>
                                    <button disabled={traceCodePage <= 1} onClick={() => { const p = traceCodePage - 1; setTraceCodePage(p); loadTraceCodes(m.id, p); }}>上一页</button>
                                    <span className="page-info">{traceCodePage} / {Math.ceil(traceTotal / tracePageSize)} 页</span>
                                    <button disabled={traceCodePage >= Math.ceil(traceTotal / tracePageSize)} onClick={() => { const p = traceCodePage + 1; setTraceCodePage(p); loadTraceCodes(m.id, p); }}>下一页</button>
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                    </React.Fragment>
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

      {/* Trace action confirm */}
      <AnimatePresence>
        {traceConfirm && (
          <motion.div className="confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="confirm-dialog glass-card" initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
              <h3>确认操作</h3>
              <p>确定要执行「{traceConfirm.label}」操作吗？</p>
              <div className="confirm-actions">
                <motion.button className={`glass-btn ${traceConfirm.type === 'delete' ? 'glass-btn--danger' : traceConfirm.type === 'unscan' ? 'glass-btn--success' : 'glass-btn--primary'}`} onClick={handleTraceConfirm} whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }}>确认</motion.button>
                <button className="glass-btn glass-btn--outline" onClick={() => setTraceConfirm(null)}>取消</button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Confirm delete */}
      <AnimatePresence>
        {confirmDelete && (
          <motion.div className="confirm-overlay" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.div className="confirm-dialog glass-card" initial={{ scale: 0.9, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.9, y: 20 }}>
              <h3>确认删除</h3>
              <p>确定要删除药品「{confirmDelete.name}」吗？此操作不可撤销。</p>
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
