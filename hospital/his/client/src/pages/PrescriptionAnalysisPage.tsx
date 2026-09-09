import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import ModuleIcon from '../components/ModuleIcon';
import { showToast } from '../components/Toast';
import { prescriptionApi } from '../services/api';
import type { PrescriptionAnalysisResult } from '../services/api';
import type { Prescription } from '../types';
import { STATUS_LABELS } from '../types';
import { formatDateTime } from '../utils/date';

const RISK_LABELS: Record<PrescriptionAnalysisResult['risk_level'], string> = {
  '低': '低风险',
  '中': '中风险',
  '高': '高风险',
  '需复核': '需人工复核',
};

export default function PrescriptionAnalysisPage() {
  const [prescriptions, setPrescriptions] = useState<Prescription[]>([]);
  const [results, setResults] = useState<Record<number, PrescriptionAnalysisResult>>({});
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(true);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const response = await prescriptionApi.list({ page: 1, pageSize: 200 });
      setPrescriptions(response.list);
    } catch (err: any) {
      showToast(err.response?.data?.error || '处方加载失败', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const filtered = useMemo(() => {
    const value = keyword.trim().toLowerCase();
    if (!value) return prescriptions;
    return prescriptions.filter((prescription) =>
      [prescription.prescription_code, prescription.patient_name, prescription.diagnosis, prescription.doctor_name]
        .some((field) => String(field || '').toLowerCase().includes(value))
    );
  }, [keyword, prescriptions]);

  const analyze = async (prescription: Prescription) => {
    setAnalyzingId(prescription.id);
    try {
      const result = await prescriptionApi.analyze(prescription.id);
      setResults((current) => ({ ...current, [prescription.id]: result }));
    } catch (err: any) {
      showToast(err.response?.data?.error || '云端 AI 分析失败', 'error');
    } finally {
      setAnalyzingId(null);
    }
  };

  return (
    <div className="prescription-ai-page">
      <motion.header className="prescription-ai-header" initial={{ opacity: 0, y: -14 }} animate={{ opacity: 1, y: 0 }}>
        <div className="prescription-ai-title">
          <span className="page-title-icon"><ModuleIcon name="prescriptionAnalysis" size={46} /></span>
          <div>
            <h1>处方智析</h1>
          </div>
        </div>
        <button className="glass-btn glass-btn--outline" onClick={load} disabled={loading}>
          {loading ? '同步中…' : '同步处方'}
        </button>
      </motion.header>

      <div className="prescription-ai-toolbar">
        <label className="prescription-ai-search" aria-label="检索处方">
          <input className="glass-input" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="处方号、患者、诊断或医生" />
        </label>
        <div className="prescription-ai-count">共 <strong>{filtered.length}</strong> 张 · 已分析 <strong>{Object.keys(results).length}</strong> 张</div>
      </div>

      {loading ? <div className="loading">正在同步处方…</div> : filtered.length === 0 ? (
        <div className="glass-card prescription-ai-empty">没有找到匹配的处方</div>
      ) : (
        <div className="prescription-ai-list">
          {filtered.map((prescription, index) => {
            const result = results[prescription.id];
            const isAnalyzing = analyzingId === prescription.id;
            return (
              <motion.article className={`prescription-ai-case ${result ? 'prescription-ai-case--analyzed' : ''}`} key={prescription.id} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(index * .035, .25) }}>
                <div className="prescription-ai-case-main">
                  <div className="prescription-ai-case-code">
                    <span>处方</span>
                    <strong>{prescription.prescription_code || `#${prescription.id}`}</strong>
                  </div>
                  <div className="prescription-ai-case-patient">
                    <strong>{prescription.patient_name || '未记录患者'}</strong>
                    <span>{prescription.diagnosis || '未填写诊断'}</span>
                  </div>
                  <div className="prescription-ai-case-meta">
                    <span>{prescription.prescription_type || '普通'}处方</span>
                    <span>{STATUS_LABELS[prescription.status]}</span>
                    <span>{formatDateTime(prescription.created_at)}</span>
                  </div>
                  <div className="prescription-ai-case-action">
                    {result && <span className={`prescription-ai-risk prescription-ai-risk--${result.risk_level}`}>· {RISK_LABELS[result.risk_level]}</span>}
                    <button className="glass-btn glass-btn--primary" disabled={analyzingId !== null} onClick={() => void analyze(prescription)}>
                      {isAnalyzing ? <><span className="prescription-ai-spinner" />分析中</> : result ? '重新分析' : '开始 AI 分析'}
                    </button>
                  </div>
                </div>

                <AnimatePresence initial={false}>
                  {result && (
                    <motion.div className="prescription-ai-result" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                      <div className="prescription-ai-result-summary">
                        <span>AI 结论</span>
                        <p>{result.summary}</p>
                        <small>{result.simulated ? '模拟结果' : result.model} · {formatDateTime(result.analyzed_at)}</small>
                      </div>
                      <AnalysisColumn title="复核要点" items={result.findings} empty="未发现明确异常要点" />
                      <AnalysisColumn title="处理建议" items={result.suggestions} empty="请结合完整病历人工复核" />
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.article>
            );
          })}
        </div>
      )}

      <p className="prescription-ai-disclaimer">AI 结果仅用于审方辅助，不代替医生或药师的专业判断。</p>
    </div>
  );
}

function AnalysisColumn({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="prescription-ai-result-column">
      <span>{title}</span>
      {items.length ? <ul>{items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul> : <p>{empty}</p>}
    </div>
  );
}
