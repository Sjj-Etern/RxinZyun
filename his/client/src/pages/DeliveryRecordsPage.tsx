import { useEffect, useRef, useState } from 'react';
import api from '../services/api';
import { useAuth } from '../hooks/useAuth';
import { showToast } from '../components/Toast';

const statusMeta: Record<string, { label: string; color: string; background: string; borderColor: string }> = {
  delivering: { label: '配送中', color: '#0369a1', background: 'rgba(14,165,233,.14)', borderColor: 'rgba(14,165,233,.34)' },
  arrived: { label: '待医生核验', color: '#b45309', background: 'rgba(245,158,11,.16)', borderColor: 'rgba(245,158,11,.38)' },
  unlocked: { label: '已核验开锁', color: '#15803d', background: 'rgba(34,197,94,.14)', borderColor: 'rgba(34,197,94,.34)' },
};

export default function DeliveryRecordsPage() {
  const { user } = useAuth();
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [verifyingRecord, setVerifyingRecord] = useState<any | null>(null);
  const [cameraReady, setCameraReady] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verificationSucceeded, setVerificationSucceeded] = useState(false);
  const [verificationMessage, setVerificationMessage] = useState('正在连接摄像头...');
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const requestInFlightRef = useRef(false);
  const verificationCompleteRef = useRef(false);
  const closeTimerRef = useRef<number | null>(null);

  const load = async () => {
    try { setRecords((await api.get('/delivery-records')).data); }
    catch (e: any) { showToast(e.response?.data?.error || '配送记录加载失败', 'error'); }
    finally { setLoading(false); }
  };

  const releaseCamera = () => {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
  };

  const closeCamera = () => {
    if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
    closeTimerRef.current = null;
    releaseCamera();
    setCameraReady(false);
    setVerifyingRecord(null);
    setVerificationSucceeded(false);
    verificationCompleteRef.current = false;
    setVerificationMessage('正在连接摄像头...');
  };

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 10000);
    return () => {
      window.clearInterval(timer);
      if (closeTimerRef.current !== null) window.clearTimeout(closeTimerRef.current);
      releaseCamera();
    };
  }, []);

  useEffect(() => {
    if (verifyingRecord && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
      videoRef.current.play().catch(() => showToast('摄像头画面无法播放，请检查浏览器权限', 'error'));
    }
  }, [verifyingRecord]);

  const arrival = async (id: number) => {
    try {
      showToast((await api.post(`/delivery-records/${id}/simulate-arrival`)).data.message, 'success');
      load();
    } catch (e: any) {
      showToast(e.response?.data?.error || '操作失败', 'error');
    }
  };

  const openCamera = async (record: any) => {
    try {
      releaseCamera();
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'user' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;
      verificationCompleteRef.current = false;
      setVerificationSucceeded(false);
      setCameraReady(false);
      setVerificationMessage('正在连接摄像头...');
      setVerifyingRecord(record);
    } catch {
      showToast('无法打开摄像头，请允许浏览器使用摄像头后重试', 'error');
    }
  };

  const verifyCurrentFrame = async () => {
    const video = videoRef.current;
    if (!verifyingRecord || !video || !cameraReady || !video.videoWidth || requestInFlightRef.current || verificationCompleteRef.current) return;
    requestInFlightRef.current = true;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d')?.drawImage(video, 0, 0);
    setVerifying(true);
    setVerificationMessage('正在实时检测并比对人脸...');
    try {
      const response = await api.post('/delivery-records/' + verifyingRecord.id + '/verify-and-unlock', { face_image: canvas.toDataURL('image/jpeg', 0.88) });
      verificationCompleteRef.current = true;
      setVerificationSucceeded(true);
      setVerificationMessage('人脸核验成功，机器人药箱已开锁，3 秒后自动关闭摄像头');
      showToast(response.data.message, 'success');
      closeTimerRef.current = window.setTimeout(closeCamera, 3000);
      await load();
    } catch (e: any) {
      const message = e.response?.data?.error || '暂未识别到匹配人脸，请正对镜头';
      setVerificationMessage(message);
      if (message.includes('请先在身份认证')) {
        showToast(message, 'error');
        closeCamera();
      }
    } finally {
      requestInFlightRef.current = false;
      setVerifying(false);
    }
  };

  useEffect(() => {
    if (!verifyingRecord || !cameraReady) return;
    void verifyCurrentFrame();
    const timer = window.setInterval(() => void verifyCurrentFrame(), 1200);
    return () => window.clearInterval(timer);
  }, [verifyingRecord, cameraReady]);

  return (
    <div>
      <style>{'.delivery-records-table th, .delivery-records-table td { text-align: center !important; vertical-align: middle !important; }'}</style>
      <div className="page-header">
        <h1>配送记录</h1>
        <p>{(user?.role === 'doctor' || user?.role === 'admin') ? '机器人到达后，打开摄像头即可实时识别人脸并自动核验开锁。' : '药师可模拟机器人到达，医生或开方管理员将自动收到待核验状态。'}</p>
      </div>

      {verifyingRecord && (
        <div className="glass-card" style={{ padding: 20, maxWidth: 760, marginBottom: 18 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div>
              <strong>实时人脸核验</strong>
              <div style={{ color: 'var(--text-muted)', fontSize: 12, marginTop: 4 }}>{verifyingRecord.medicine_name} · {verifyingRecord.robot_code}</div>
            </div>
            <span className="glass-badge" style={{ color: verificationSucceeded ? '#15803d' : verifying ? '#0369a1' : '#b45309' }}>
              {verificationSucceeded ? '核验成功' : verifying ? '实时比对中' : cameraReady ? '等待识别' : '连接摄像头'}
            </span>
          </div>
          <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 20, background: '#061923', aspectRatio: '16 / 9' }}>
            <video ref={videoRef} autoPlay playsInline muted onLoadedMetadata={() => setCameraReady(true)} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', transform: 'scaleX(-1)' }} />
            <div style={{ position: 'absolute', inset: 16, border: '2px solid rgba(255,255,255,.78)', borderRadius: '50%', width: '30%', height: '64%', margin: 'auto', pointerEvents: 'none', boxShadow: '0 0 0 999px rgba(3,19,29,.18)' }} />
            <div style={{ position: 'absolute', left: 16, bottom: 16, color: 'white', fontSize: 13, fontWeight: 600 }}>
              {verificationSucceeded ? '✓ 人脸核验成功，药箱已开锁' : cameraReady ? '● 正在实时检测，请正对镜头并保持稳定' : '● 正在连接摄像头...'}
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, marginTop: 16 }}>
            <div style={{ color: verificationSucceeded ? '#15803d' : verifying ? '#0369a1' : 'var(--text-muted)', fontSize: 13 }}>{verificationMessage}</div>
            <button className="glass-btn glass-btn--outline" disabled={verificationSucceeded} onClick={closeCamera}>取消核验</button>
          </div>
        </div>
      )}

      <div className="glass-card" style={{ padding: 20 }}>
        <button className="glass-btn glass-btn--outline glass-btn--sm" onClick={load}>刷新</button>
        {loading ? (
          <div className="loading">加载中...</div>
        ) : (
          <table className="glass-table delivery-records-table" style={{ width: '100%', marginTop: 12 }}>
            <thead>
              <tr>
                <th>处方</th>
                <th>病人</th>
                <th>药品</th>
                <th>配送机器人</th>
                <th>状态</th>
                <th>配送/核验人</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {records.map(r => (
                <tr key={r.id}>
                  <td>{r.prescription_code || `#${r.prescription_id}`}</td>
                  <td>{r.patient_name}</td>
                  <td>{r.medicine_name} × {r.quantity}{r.unit}</td>
                  <td>{r.robot_code} · {r.robot_name}</td>
                  <td>
                    <span className="glass-badge" style={{
                      color: (statusMeta[r.status] || statusMeta.delivering).color,
                      background: (statusMeta[r.status] || statusMeta.delivering).background,
                      borderColor: (statusMeta[r.status] || statusMeta.delivering).borderColor,
                      fontWeight: 700
                    }}>
                      {(statusMeta[r.status] || statusMeta.delivering).label}
                    </span>
                  </td>
                  <td>{r.dispatched_by_name}{r.verified_by_name ? ` / ${r.verified_by_name}` : ''}</td>
                  <td>
                    {(user?.role === 'pharmacist' || user?.role === 'admin') && r.status === 'delivering' && (
                      <button className="glass-btn glass-btn--primary glass-btn--sm" onClick={() => arrival(r.id)}>模拟到达</button>
                    )}
                    {(user?.role === 'doctor' || user?.role === 'admin') && r.status === 'arrived' && (
                      <button className="glass-btn glass-btn--success glass-btn--sm" onClick={() => openCamera(r)}>打开摄像头核验</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!loading && !records.length && (
          <div className="empty-state"><p>暂无配送记录</p></div>
        )}
      </div>
    </div>
  );
}