import { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuth } from '../hooks/useAuth';
import ToastContainer from './Toast';
import ModuleIcon, { type ModuleIconName } from './ModuleIcon';

const ROLES: Record<string,string> = { doctor:'医生', pharmacist:'药师', admin:'管理员' };

type TabItem = {
  to: string;
  icon: ModuleIconName;
  label: string;
  roles?: string[];
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const t = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // ── 第7层: 前端定时轮询检查 ──
  useEffect(() => {
    const check = () => {
      const d = new Date();
      const v = d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
      if (v > 20261231) {
        logout();
        navigate('/login');
      }
    };
    const t = setInterval(check, 30000);
    check(); // 挂载时立刻检查一次
    return () => clearInterval(t);
  }, [logout, navigate]);

  const fmt = (d:Date) => {
    const y=d.getFullYear(), m=String(d.getMonth()+1).padStart(2,'0'), da=String(d.getDate()).padStart(2,'0');
    const h=String(d.getHours()).padStart(2,'0'), mi=String(d.getMinutes()).padStart(2,'0'), s=String(d.getSeconds()).padStart(2,'0');
    return `${y}-${m}-${da} ${h}:${mi}:${s}`;
  };

  const allTabs: TabItem[] = [
    { to:'/dashboard', icon:'dashboard', label:'工作版' },
    { to:'/prescriptions/new', icon:'prescriptionNew', label:'开具处方', roles:['doctor','admin'] },
    { to:'/review', icon:'review', label:'处方审核', roles:['pharmacist','admin'] },
    { to:'/patients', icon:'patients', label:'病人管理' },
    { to:'/medicines', icon:'medicines', label:'药品管理' },
  ];
  const tabs = allTabs.filter(t => !t.roles || (user&&t.roles.includes(user.role)));

  return (
    <div>
      <header className="topbar">
        <h1><span className="brand-mark">H</span><span>仁爱医院 HIS</span></h1>
        <div className="topbar-right">
          <span className="topbar-time">{fmt(time)}</span>
          <span className="topbar-role">{ROLES[user?.role||'']}</span>
          <span className="topbar-user">{user?.real_name}</span>
          <button className="topbar-logout" onClick={()=>{logout();navigate('/login');}}>退出</button>
        </div>
      </header>

      <nav className="tabbar">
        {tabs.map(t => (
          <button key={t.to} className={`tab ${loc.pathname===t.to?'tab--active':''}`}
            onClick={()=>navigate(t.to)}>
            <span className="tab-icon" aria-hidden="true"><ModuleIcon name={t.icon} size={24} /></span> {t.label}
          </button>
        ))}
      </nav>

      <main className="content">
        <motion.div key={loc.pathname} initial={{opacity:0,y:10}} animate={{opacity:1,y:0}} transition={{duration:0.2}}>
          {children}
        </motion.div>
      </main>

      {/* Toast notifications */}
      <ToastContainer />

      {/* Floating scan button */}
      <motion.button
        onClick={() => navigate('/scan')}
        className="scan-fab"
        whileHover={{ scale: 1.08 }}
        whileTap={{ scale: 0.92 }}
        initial={{ scale: 0, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ delay: 0.5, type: 'spring', stiffness: 300 }}
      >
        <ModuleIcon name="scan" size={42} />
      </motion.button>
    </div>
  );
}
