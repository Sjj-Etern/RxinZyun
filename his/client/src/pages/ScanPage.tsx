import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { Html5Qrcode } from 'html5-qrcode';
import { medicineTraceCodeApi } from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { formatDateTime } from '../utils/date';

interface ScanEntry {
  trace_code: string;
  medicine_name: string;
  status: string;
  action: string;
  scan1_time: string | null;
  scan2_time: string | null;
  scan3_time: string | null;
  time: string;
}

const playBeep = () => {
  try {
    const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.value = 800; osc.type = 'sine';
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
    osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.15);
  } catch (e) {}
};

const STATUS_LABEL: Record<string, string> = {
  pending: '待扫描', scanned_identify: '已识别', scanned_outbound: '已出库', scanned_confirm: '已完成'
};

const getTraceCodeCandidates = (value: string) => {
  const raw = value.trim();
  if (!raw) return [];
  const candidates = new Set<string>([raw]);

  try {
    const decoded = decodeURIComponent(raw);
    if (decoded) candidates.add(decoded.trim());
  } catch (e) {}

  try {
    const url = new URL(raw);
    ['trace_code', 'traceCode', 'code', 'c'].forEach((key) => {
      const paramValue = url.searchParams.get(key);
      if (paramValue) candidates.add(paramValue.trim());
    });
  } catch (e) {}

  for (const text of Array.from(candidates)) {
    const compact = text.replace(/[\s-]/g, '');
    if (/^\d{20,}$/.test(compact)) candidates.add(compact);
    const digitMatches = text.match(/\d{20,}/g) || [];
    digitMatches.forEach((match) => candidates.add(match));
  }

  return Array.from(candidates).filter(Boolean);
};

const normalizeTraceCodeInput = (value: string) => {
  const candidates = getTraceCodeCandidates(value);
  return candidates.find((candidate) => /^\d{20,}$/.test(candidate)) || candidates[0] || value.trim();
};

export default function ScanPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const [history, setHistory] = useState<ScanEntry[]>([]);
  const [searchCode, setSearchCode] = useState('');
  const [searchResult, setSearchResult] = useState<ScanEntry | null>(null);

  const scannerRef = useRef<Html5Qrcode | null>(null);
  const busyRef = useRef(false);
  const lastCodeRef = useRef('');
  const historyRef = useRef<ScanEntry[]>([]);

  // Keep historyRef in sync
  historyRef.current = history;

  const processCodeRef = useRef<(code: string) => void>(() => {});

  const stopScanner = async () => {
    if (scannerRef.current) {
      try { await scannerRef.current.stop(); } catch (e) {}
    }
    setScanning(false);
  };

  const startScanner = async () => {
    setError('');
    const el = document.getElementById('scanner-view');
    if (!el) return;
    el.innerHTML = '';

    if (scannerRef.current) {
      try { await scannerRef.current.stop(); } catch (e) {}
    }

    try {
      scannerRef.current = new Html5Qrcode('scanner-view');
      await scannerRef.current.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 280, height: 100 } },
        (decodedText: string) => {
          const code = normalizeTraceCodeInput(decodedText);
          if (code) processCodeRef.current(code);
        },
        () => {}
      );
      setScanning(true);
    } catch (err: any) {
      const msg = err.message || '';
      if (msg.includes('NotAllowed') || msg.includes('Permission')) {
        setError('摄像头权限未开启');
      } else {
        setError('启动失败: ' + msg);
      }
    }
  };

  const processCode = async (code: string) => {
    const normalizedCode = normalizeTraceCodeInput(code);
    if (busyRef.current || normalizedCode === lastCodeRef.current) return;
    busyRef.current = true;
    lastCodeRef.current = normalizedCode;

    try {
      const data = await medicineTraceCodeApi.scanByCode(normalizedCode);
      playBeep();
      const newEntry: ScanEntry = {
        trace_code: data.trace_code || normalizedCode,
        medicine_name: data.medicine_name || '',
        status: data.status || '',
        action: data.action || '',
        scan1_time: data.scan1_time || null,
        scan2_time: data.scan2_time || null,
        scan3_time: data.scan3_time || null,
        time: formatDateTime(new Date()),
      };
      setHistory(prev => {
        const others = prev.filter(e => e.trace_code !== newEntry.trace_code);
        return [newEntry, ...others];
      });
      setToast({ text: (data.completed ? '已完成' : data.action + '成功'), type: 'success' });
    } catch (err: any) {
      const msg = err.response?.data?.error || '未找到';
      setToast({ text: msg, type: 'error' });
    } finally {
      // API 返回后立即释放 busy，让不同追溯码（第二个药）能马上扫码，
      // 不再像之前那样把所有码锁住 10 秒导致连扫被吞、节点3卡在 1/2
      busyRef.current = false;
    }

    // 仅保留同码去重窗口：防止摄像头对同一追溯码连续重发；3 秒足够移走药盒，
    // 且不再阻塞不同码（扫第二个药时 lastCodeRef 不同，busy 已释放，可立即处理）
    setTimeout(() => {
      lastCodeRef.current = '';
    }, 3000);

    setTimeout(() => setToast(null), 2000);
  };

  processCodeRef.current = processCode;

  useEffect(() => { return () => { stopScanner(); }; }, []);

  const handleSearch = async () => {
    if (!searchCode.trim()) return;
    const normalizedCode = normalizeTraceCodeInput(searchCode);
    try {
      const res = await fetch('/api/medicine-trace-codes/scan-by-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('token')}` },
        body: JSON.stringify({ trace_code: normalizedCode }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || '未找到');
      setSearchResult({
        trace_code: data.trace_code || normalizedCode,
        medicine_name: data.medicine_name || '',
        status: data.status || '',
        action: '',
        scan1_time: data.scan1_time || null,
        scan2_time: data.scan2_time || null,
        scan3_time: data.scan3_time || null,
        time: '',
      });
    } catch (err: any) {
      setSearchResult(null);
      setToast({ text: err.message || '未找到', type: 'error' });
      setTimeout(() => setToast(null), 2000);
    }
  };

  return (
    <div className="scan-app">
      <style>{`
        .scan-app { position: fixed; inset: 0; background: #0a0a1a; display: flex; flex-direction: column; z-index: 9999; }
        .scan-topbar { height: 48px; display: flex; align-items: center; justify-content: space-between; padding: 0 16px; color: #fff; flex-shrink: 0; }
        .scan-topbar h1 { font-size: 16px; font-weight: 600; }
        .scan-topbar button { background: linear-gradient(135deg, rgba(255,255,255,0.18), rgba(255,255,255,0.06)); border: 1px solid rgba(255,255,255,0.24); color: #fff; padding: 6px 14px; border-radius: 20px; font-size: 13px; cursor: pointer; box-shadow: inset 0 1px 0 rgba(255,255,255,0.18), 0 8px 20px rgba(0,0,0,0.2); backdrop-filter: blur(16px) saturate(160%); -webkit-backdrop-filter: blur(16px) saturate(160%); }
        .scan-camera-area { position: relative; flex-shrink: 0; }
        #scanner-view { width: 100%; min-height: 200px; background: #000; }
        #scanner-view video { width: 100% !important; height: auto !important; display: block; }
        #scanner-view canvas { display: none; }
        .scan-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; pointer-events: none; z-index: 10; }
        .scan-box { width: 280px; max-width: 85%; height: 80px; border: 2px solid rgba(74,144,217,0.7); border-radius: 8px; position: relative; }
        .scan-box::before, .scan-box::after { content: ''; position: absolute; width: 18px; height: 18px; border-color: #4A90D9; border-style: solid; }
        .scan-box::before { top: -2px; left: -2px; border-width: 4px 0 0 4px; border-radius: 4px 0 0 0; }
        .scan-box::after { bottom: -2px; right: -2px; border-width: 0 4px 4px 0; border-radius: 0 0 4px 0; }
        .scan-ctrl { padding: 10px 16px; flex-shrink: 0; display: flex; gap: 8px; }
        .scan-ctrl input { flex: 1; height: 40px; border-radius: 10px; border: 1px solid rgba(255,255,255,0.15); background: rgba(255,255,255,0.06); color: #fff; padding: 0 12px; font-size: 14px; outline: none; }
        .scan-ctrl input::placeholder { color: rgba(255,255,255,0.3); }
        .scan-ctrl button { height: 40px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.24); color: #fff; font-size: 14px; cursor: pointer; padding: 0 14px; background: linear-gradient(135deg, rgba(255,255,255,0.18), rgba(255,255,255,0.06)); box-shadow: inset 0 1px 0 rgba(255,255,255,0.18), 0 8px 20px rgba(0,0,0,0.2); backdrop-filter: blur(16px) saturate(160%); -webkit-backdrop-filter: blur(16px) saturate(160%); }
        .btn-scan { flex: 1; background: linear-gradient(135deg, rgba(74,144,217,0.44), rgba(45,109,181,0.22)); font-weight: 600; font-size: 15px; height: 44px; }
        .btn-stop { flex: 1; background: linear-gradient(135deg, rgba(255,255,255,0.12), rgba(255,255,255,0.04)); height: 44px; font-size: 15px; }
        .btn-search { background: linear-gradient(135deg, rgba(74,144,217,0.26), rgba(255,255,255,0.08)); flex-shrink: 0; }
        .scan-list { flex: 1; overflow-y: auto; padding: 0 16px 16px; }
        .scan-list-title { font-size: 12px; color: rgba(255,255,255,0.3); padding: 8px 0; }
        .scan-list-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; background: rgba(255,255,255,0.04); border-radius: 10px; margin-bottom: 6px; }
        .scan-list-item .code { font-size: 11px; color: rgba(255,255,255,0.4); font-family: monospace; word-break: break-all; }
        .scan-list-item .name { font-size: 14px; color: #fff; font-weight: 600; }
        .scan-list-item .tag { font-size: 10px; padding: 2px 8px; border-radius: 8px; flex-shrink: 0; }
        .scan-list-item .time { font-size: 10px; color: rgba(255,255,255,0.25); }
        .scan-empty { text-align: center; color: rgba(255,255,255,0.15); padding: 40px 0; font-size: 14px; }
        .scan-toast { position: fixed; top: 60px; left: 50%; transform: translateX(-50%); z-index: 99999; padding: 10px 24px; border-radius: 50px; font-size: 15px; font-weight: 600; color: #fff; white-space: nowrap; box-shadow: 0 8px 32px rgba(0,0,0,0.4); }
        .scan-toast.success { background: linear-gradient(135deg, #5CB85C, #3D8B3D); }
        .scan-toast.error { background: linear-gradient(135deg, #DC2626, #B91C1C); }
      `}</style>

      <div className="scan-topbar">
        <button onClick={() => navigate(-1)}>返回</button>
        <h1>扫码核验</h1>
        <button onClick={() => { stopScanner(); logout(); navigate('/login'); }}>退出</button>
      </div>

      <div className="scan-camera-area">
        <div id="scanner-view" />
        {scanning && (
          <div className="scan-overlay">
            <div className="scan-box" />
          </div>
        )}
        {!scanning && (
          <div className="scan-overlay" style={{ background: 'rgba(0,0,0,0.3)' }}>
            <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 14 }}>点击下方按钮启动扫码</div>
          </div>
        )}
      </div>

      <div className="scan-ctrl">
        {!scanning ? (
          <button className="btn-scan" onClick={startScanner}>启动扫码</button>
        ) : (
          <button className="btn-stop" onClick={stopScanner}>停止扫码</button>
        )}
      </div>

      {/* Search input */}
      <div className="scan-ctrl" style={{ paddingTop: 0 }}>
        <input
          placeholder="手动输入追溯码查询..."
          value={searchCode}
          onChange={e => setSearchCode(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
        />
        <button className="btn-search" onClick={handleSearch}>搜索</button>
      </div>

      {/* Search result */}
      {searchResult && (
        <div style={{ padding: '0 16px 8px' }}>
          <div className="scan-list-item" style={{ border: '1px solid rgba(74,144,217,0.3)' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="name">{searchResult.medicine_name}</div>
              <div className="code">{searchResult.trace_code}</div>
            </div>
            <span className="tag" style={{
              background: searchResult.status === 'scanned_confirm' ? 'rgba(142,68,173,0.3)'
                : searchResult.status === 'scanned_outbound' ? 'rgba(92,184,92,0.3)'
                : searchResult.status === 'scanned_identify' ? 'rgba(74,144,217,0.3)'
                : 'rgba(240,173,78,0.3)',
              color: searchResult.status === 'scanned_confirm' ? '#B07CD8'
                : searchResult.status === 'scanned_outbound' ? '#5CB85C'
                : searchResult.status === 'scanned_identify' ? '#4A90D9'
                : '#F0AD4E',
            }}>{STATUS_LABEL[searchResult.status] || searchResult.status}</span>
          </div>
        </div>
      )}

      {error && <div style={{ color: '#EF4444', fontSize: 13, textAlign: 'center', padding: '4px 16px' }}>{error}</div>}

      <div className="scan-list">
        <div className="scan-list-title">扫码记录 ({history.length})</div>
        {history.length === 0 ? (
          <div className="scan-empty">暂无扫码记录</div>
        ) : (
          history.map((entry, i) => (
            <div key={entry.trace_code + '-' + i} className="scan-list-item">
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="name">{entry.medicine_name}</div>
                <div className="code">{entry.trace_code}</div>
              </div>
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <span className="tag" style={{
                  background: entry.status === 'scanned_confirm' ? 'rgba(142,68,173,0.3)'
                    : entry.status === 'scanned_outbound' ? 'rgba(92,184,92,0.3)'
                    : entry.status === 'scanned_identify' ? 'rgba(74,144,217,0.3)'
                    : 'rgba(240,173,78,0.3)',
                  color: entry.status === 'scanned_confirm' ? '#B07CD8'
                    : entry.status === 'scanned_outbound' ? '#5CB85C'
                    : entry.status === 'scanned_identify' ? '#4A90D9'
                    : '#F0AD4E',
                }}>{STATUS_LABEL[entry.status] || entry.action}</span>
                <div className="time" style={{ marginTop: 2 }}>{entry.time}</div>
              </div>
            </div>
          ))
        )}
      </div>

      <AnimatePresence>
        {toast && (
          <motion.div
            className={`scan-toast ${toast.type}`}
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
          >
            {toast.text}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
