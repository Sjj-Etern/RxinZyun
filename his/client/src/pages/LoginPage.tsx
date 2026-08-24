import { useState, FormEvent } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { authApi } from '../services/api';
import { useAuth } from '../hooks/useAuth';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { user, login } = useAuth();
  const navigate = useNavigate();

  if (user) return <Navigate to="/dashboard" replace />;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    if (!username || !password) { setError('请输入用户名和密码'); return; }
    setLoading(true);
    try {
      const data = await authApi.login(username, password);
      login(data.user, data.token);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err.response?.data?.error || '登录失败，请重试');
    } finally { setLoading(false); }
  };

  return (
    <div className="login-page">
      <motion.form
        className="login-card glass-card"
        onSubmit={handleSubmit}
        initial={{ opacity: 0, scale: 0.9, y: 30 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', damping: 20, stiffness: 200 }}
      >
        <motion.h2 initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
          <span className="login-brand-mark">H</span>
          医院HIS系统
        </motion.h2>
        <motion.p className="subtitle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.15 }}>
          医生配药管理平台
        </motion.p>

        {error && (
          <motion.div className="alert alert--error" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}>
            {error}
          </motion.div>
        )}

        <motion.div className="form-group" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
          <label>用户名</label>
          <input className="glass-input" type="text" placeholder="请输入用户名" value={username}
            onChange={(e) => setUsername(e.target.value)} autoFocus />
        </motion.div>

        <motion.div className="form-group" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}>
          <label>密码</label>
          <input className="glass-input" type="password" placeholder="请输入密码" value={password}
            onChange={(e) => setPassword(e.target.value)} />
        </motion.div>

        <motion.button
          className="glass-btn glass-btn--primary glass-btn--lg"
          type="submit" disabled={loading}
          initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
        >
          {loading ? '登录中...' : '登 录'}
        </motion.button>

        <p style={{ textAlign: 'center', marginTop: 16, fontSize: 12, color: 'var(--text-muted)' }}>
          测试账号：doctor1 / pharmacist1 / admin · 密码 123456
        </p>
      </motion.form>
    </div>
  );
}
