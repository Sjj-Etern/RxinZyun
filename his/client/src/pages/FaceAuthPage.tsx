import { useEffect, useRef, useState } from 'react';
import api from '../services/api';
import { showToast } from '../components/Toast';

export default function FaceAuthPage() {
  const [enrolled, setEnrolled] = useState(false);
  const [image, setImage] = useState('');
  const [saving, setSaving] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach(track => track.stop());
    streamRef.current = null;
    setCameraReady(false);
    setCameraOpen(false);
  };

  useEffect(() => {
    api.get('/face-profiles').then(r => setEnrolled(Boolean(r.data.enrolled))).catch(() => {});
    return stopCamera;
  }, []);

  useEffect(() => {
    if (cameraOpen && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current;
      videoRef.current.play().catch(() => showToast('摄像头画面无法播放，请检查浏览器权限', 'error'));
    }
  }, [cameraOpen]);

  const openCamera = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'user' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;
      setCameraReady(false);
      setCameraOpen(true);
    } catch {
      showToast('无法打开摄像头，请允许浏览器使用摄像头后重试', 'error');
    }
  };

  const capture = () => {
    const video = videoRef.current;
    if (!video || !cameraReady || !video.videoWidth) return showToast('正在连接摄像头，请稍候', 'error');
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d')?.drawImage(video, 0, 0);
    setImage(canvas.toDataURL('image/jpeg', 0.88));
    stopCamera();
    showToast('人脸采集成功，请确认后保存', 'success');
  };

  const save = async () => {
    if (!image) return showToast('请先采集人脸', 'error');
    setSaving(true);
    try {
      const r = await api.put('/face-profiles', { face_image: image });
      setEnrolled(true);
      showToast(r.data.message, 'success');
    } catch (e: any) {
      showToast(e.response?.data?.error || '录入失败', 'error');
    } finally {
      setSaving(false);
    }
  };

  return <div>
    <div className="page-header"><h1>身份认证</h1><p>直接采集本机摄像头画面，用于机器人送药时的本人核验。</p></div>
    <div className="glass-card" style={{ padding: 24, maxWidth: 760 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 18 }}>
        <span className="glass-badge" style={{ color: enrolled ? '#15803d' : '#b45309' }}>{enrolled ? '已录入人脸' : '未录入人脸'}</span>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>正对镜头，保持光线充足；画面显示后即可拍摄。</span>
      </div>
      {cameraOpen ? <div style={{ position: 'relative', overflow: 'hidden', borderRadius: 20, background: '#061923', aspectRatio: '16 / 9' }}>
        <video ref={videoRef} autoPlay playsInline muted onLoadedMetadata={() => setCameraReady(true)} style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
        <div style={{ position: 'absolute', inset: 16, border: '2px solid rgba(255,255,255,.78)', borderRadius: '50%', width: '30%', height: '64%', margin: 'auto', pointerEvents: 'none', boxShadow: '0 0 0 999px rgba(3,19,29,.18)' }} />
        <div style={{ position: 'absolute', left: 16, bottom: 16, color: 'white', fontSize: 13, fontWeight: 600 }}>{cameraReady ? '● 摄像头已就绪，请将脸部置于取景框内' : '● 正在连接摄像头...'}</div>
      </div> : image ? <div style={{ display: 'flex', gap: 20, alignItems: 'center', padding: 16, borderRadius: 18, background: 'rgba(56,191,193,.08)' }}><img src={image} alt="已采集的人脸" style={{ width: 160, height: 160, objectFit: 'cover', borderRadius: 16 }} /><div><strong style={{ color: '#15803d' }}>人脸采集成功</strong><p style={{ color: 'var(--text-muted)', fontSize: 13 }}>确认是本人照片后，保存到当前账户。</p></div></div> : <div style={{ padding: '42px 20px', textAlign: 'center', border: '1px dashed rgba(56,191,193,.45)', borderRadius: 20, color: 'var(--text-muted)' }}>尚未打开摄像头</div>}
      <div style={{ display: 'flex', gap: 10, marginTop: 18 }}>
        {cameraOpen ? <><button className="glass-btn glass-btn--primary" onClick={capture} disabled={!cameraReady}>拍摄人脸</button><button className="glass-btn glass-btn--outline" onClick={stopCamera}>取消</button></> : <button className="glass-btn glass-btn--outline" onClick={openCamera}>{image ? '重新拍摄' : '打开摄像头'}</button>}
        {!cameraOpen && <button className="glass-btn glass-btn--primary" onClick={save} disabled={!image || saving}>{saving ? '保存中...' : enrolled ? '更新人脸信息' : '保存人脸信息'}</button>}
      </div>
    </div>
  </div>;
}