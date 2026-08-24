import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { medicineTraceCodeApi } from '../services/api';
import { formatDateTime } from '../utils/date';
import ModuleIcon from '../components/ModuleIcon';

interface TraceEntry {
  id: string;
  trace_code: string;
  medicine_name: string;
  status: string;
  action: string;
  scan1_time: string | null;
  scan2_time: string | null;
  scan3_time: string | null;
  time: string;
  kind?: 'scan' | 'error';
  message?: string;
}

const STATUS_LABEL: Record<string, string> = {
  pending: '待出库',
  scanned_outbound: '已出库',
  scanned_confirm: '已完成',
  scanned_identify: '待出库（旧状态）',
  error: '扫码失败',
};

const STATUS_TONE: Record<string, string> = {
  pending: 'pending',
  scanned_outbound: 'outbound',
  scanned_confirm: 'complete',
  scanned_identify: 'pending',
  error: 'error',
};

const getTraceCodeCandidates = (value: string) => {
  const raw = value.trim();
  if (!raw) return [];
  const candidates = new Set<string>([raw]);

  try {
    const decoded = decodeURIComponent(raw);
    if (decoded) candidates.add(decoded.trim());
  } catch {
    // 保留原始输入，交给后端返回明确错误。
  }

  try {
    const url = new URL(raw);
    ['trace_code', 'traceCode', 'code', 'c'].forEach((key) => {
      const paramValue = url.searchParams.get(key);
      if (paramValue) candidates.add(paramValue.trim());
    });
  } catch {
    // 普通追溯码不是 URL 时忽略解析错误。
  }

  for (const text of Array.from(candidates)) {
    const compact = text.replace(/[\s-]/g, '');
    if (/^\d{20,}$/.test(compact)) candidates.add(compact);
    (text.match(/\d{20,}/g) || []).forEach((match) => candidates.add(match));
  }

  return Array.from(candidates).filter(Boolean);
};

const normalizeTraceCodeInput = (value: string) => {
  const candidates = getTraceCodeCandidates(value);
  return candidates.find((candidate) => /^\d{20,}$/.test(candidate)) || candidates[0] || value.trim();
};

const toEntry = (data: any, fallbackCode: string, action = ''): TraceEntry => ({
  id: `${fallbackCode}-${Date.now()}`,
  trace_code: data.trace_code || fallbackCode,
  medicine_name: data.medicine_name || '未命名药品',
  status: data.status || 'pending',
  action: data.action || action,
  scan1_time: data.scan1_time || null,
  scan2_time: data.scan2_time || null,
  scan3_time: data.scan3_time || null,
  time: formatDateTime(new Date()),
  kind: 'scan',
});

const playBeep = () => {
  try {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    const context = new AudioContextClass();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.frequency.value = 820;
    oscillator.type = 'sine';
    gain.gain.setValueAtTime(0.22, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.14);
    oscillator.start(context.currentTime);
    oscillator.stop(context.currentTime + 0.14);
  } catch {
    // 浏览器禁止音频时不影响扫码流程。
  }
};

export default function ScanPage() {
  const [history, setHistory] = useState<TraceEntry[]>([]);
  const [searchCode, setSearchCode] = useState('');
  const [searchResult, setSearchResult] = useState<TraceEntry | null>(null);
  const [searchError, setSearchError] = useState('');
  const [toast, setToast] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const [processing, setProcessing] = useState(false);

  const busyRef = useRef(false);
  const lastCodeRef = useRef('');
  const barcodeBufferRef = useRef('');
  const barcodeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const processCodeRef = useRef<(code: string) => void>(() => {});

  const showToast = (text: string, type: 'success' | 'error') => {
    setToast({ text, type });
    window.setTimeout(() => setToast(null), 2200);
  };

  const processCode = async (value: string) => {
    const code = normalizeTraceCodeInput(value);
    if (!code || busyRef.current || code === lastCodeRef.current) return;

    busyRef.current = true;
    lastCodeRef.current = code;
    setProcessing(true);
    setSearchError('');

    try {
      const data = await medicineTraceCodeApi.scanByCode(code);
      const entry = toEntry(data, code, data.action || '扫码');
      setHistory((current) => [entry, ...current.filter((item) => item.trace_code !== entry.trace_code)]);
      setSearchResult(entry);
      playBeep();
      showToast(data.completed ? '追溯码已完成全部流程' : `${data.action || '扫码'}成功`, 'success');
    } catch (err: any) {
      const message = err.response?.data?.error || err.message || '扫码失败，请重试';
      setHistory((current) => [{
        id: `error-${Date.now()}`,
        trace_code: code,
        medicine_name: '扫码失败',
        status: 'error',
        action: '扫码失败',
        scan1_time: null,
        scan2_time: null,
        scan3_time: null,
        time: formatDateTime(new Date()),
        kind: 'error',
        message,
      }, ...current]);
    } finally {
      busyRef.current = false;
      setProcessing(false);
      window.setTimeout(() => {
        if (lastCodeRef.current === code) lastCodeRef.current = '';
      }, 1200);
    }
  };

  processCodeRef.current = processCode;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;

      if (event.key === 'Enter') {
        const value = barcodeBufferRef.current;
        barcodeBufferRef.current = '';
        if (value) void processCodeRef.current(value);
        return;
      }

      if (event.key.length !== 1) return;
      barcodeBufferRef.current += event.key;
      if (barcodeTimerRef.current) clearTimeout(barcodeTimerRef.current);
      barcodeTimerRef.current = setTimeout(() => {
        const value = barcodeBufferRef.current;
        barcodeBufferRef.current = '';
        if (value.length >= 7) void processCodeRef.current(value);
      }, 140);
    };

    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      if (barcodeTimerRef.current) clearTimeout(barcodeTimerRef.current);
    };
  }, []);

  const handleLookup = async () => {
    const code = normalizeTraceCodeInput(searchCode);
    if (!code) return;
    setSearchError('');
    try {
      const data = await medicineTraceCodeApi.lookup(code);
      setSearchResult(toEntry(data, code));
    } catch (err: any) {
      setSearchResult(null);
      const message = err.response?.data?.error || err.message || '追溯码未找到';
      setSearchError(message);
      showToast(message, 'error');
    }
  };

  return (
    <div className="outbound-page">
      <div className="page-header outbound-page__header">
        <div>
          <div className="outbound-eyebrow"><span className="outbound-eyebrow__dot" /> TRACE DESK / 出库工作台</div>
          <h1>出库追溯</h1>
          <p>使用扫码枪完成药品出库与接收确认，实时保留本次操作记录。</p>
        </div>
      </div>

      <section className="outbound-search glass-card">
        <div className="outbound-search__label">手动查询追溯码</div>
        <div className="outbound-search__row">
          <div className="outbound-search__input-wrap">
            <span className="outbound-search__prefix">码</span>
            <input
              className="outbound-search__input"
              value={searchCode}
              onChange={(event) => setSearchCode(event.target.value)}
              onKeyDown={(event) => event.key === 'Enter' && void handleLookup()}
              placeholder="输入追溯码，仅查询当前状态，不推进流程"
              aria-label="手动查询追溯码"
            />
          </div>
          <button className="glass-btn glass-btn--primary outbound-search__button" onClick={handleLookup}>查询状态</button>
        </div>
        {searchResult && (
          <motion.div className="outbound-search-result" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}>
            <div>
              <span className="outbound-result__label">查询结果</span>
              <strong>{searchResult.medicine_name}</strong>
              <code>{searchResult.trace_code}</code>
            </div>
            <span className={`outbound-status outbound-status--${STATUS_TONE[searchResult.status] || 'pending'}`}>
              {STATUS_LABEL[searchResult.status] || searchResult.status}
            </span>
          </motion.div>
        )}
        {searchError && <div className="outbound-error">{searchError}</div>}
      </section>

      <section className="outbound-workspace">
        <motion.div className="outbound-station glass-card" whileHover={{ y: -3 }}>
          <div className="outbound-station__halo outbound-station__halo--one" />
          <div className="outbound-station__halo outbound-station__halo--two" />
          <div className="outbound-station__content">
            <div className={`outbound-scanner-icon ${processing ? 'is-processing' : ''}`}>
              <ModuleIcon name="scannerGun" size={138} />
            </div>
            <h2>请使用扫码枪扫码</h2>
            <p>将光标移出输入框，扫码枪读取追溯码后会自动提交。</p>
            {processing && <div className="outbound-station__status"><span className="outbound-station__status-dot" />正在写入出库记录…</div>}
          </div>
          <div className="outbound-station__footer"><span>每次扫码推进一个业务节点</span><span>2 次完成闭环</span></div>
        </motion.div>

        <section className="outbound-history glass-card">
          <div className="outbound-history__header">
            <div>
              <div className="outbound-eyebrow">LIVE LOG / 实时记录</div>
              <h2>扫码记录</h2>
            </div>
            <span className="outbound-history__count">{history.length.toString().padStart(2, '0')} 条</span>
          </div>
          <div className="outbound-history__list">
            <AnimatePresence initial={false} mode="popLayout">
              {history.length === 0 ? (
                <motion.div className="outbound-history__empty" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <ModuleIcon name="scannerGun" size={58} />
                  <strong>等待第一条扫码记录</strong>
                  <span>扫描成功后，记录会从这里弹出</span>
                </motion.div>
              ) : history.map((entry, index) => (
                <motion.div
                  layout
                  key={entry.id}
                  className={`outbound-entry ${entry.kind === 'error' ? 'outbound-entry--error' : ''} ${index === 0 ? 'outbound-entry--latest' : ''}`}
                  initial={{ opacity: 0, scale: 0.78, y: -22 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.86, y: 12 }}
                  transition={{ type: 'spring', stiffness: 430, damping: 22 }}
                >
                  <div className="outbound-entry__index">{String(index + 1).padStart(2, '0')}</div>
                  <div className="outbound-entry__main">
                    <strong>{entry.kind === 'error' ? entry.message : entry.medicine_name}</strong>
                    <code>{entry.trace_code}</code>
                    <span>{entry.time}</span>
                  </div>
                  <span className={`outbound-status outbound-status--${STATUS_TONE[entry.status] || 'pending'}`}>
                    {STATUS_LABEL[entry.status] || entry.action || '已记录'}
                  </span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </section>
      </section>

      <AnimatePresence>
        {toast && (
          <motion.div className={`outbound-toast outbound-toast--${toast.type}`} initial={{ opacity: 0, y: 20, scale: 0.9 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10, scale: 0.92 }}>
            {toast.text}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
