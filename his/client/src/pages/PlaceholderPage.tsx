import { motion } from 'framer-motion';
import ModuleIcon, { type ModuleIconName } from '../components/ModuleIcon';

interface Props { title: string; icon: ModuleIconName; }

export default function PlaceholderPage({ title, icon }: Props) {
  return (
    <motion.div style={{ textAlign: 'center', paddingTop: 80 }} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
      <div className="placeholder-icon"><ModuleIcon name={icon} size={64} /></div>
      <h2 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8 }}>{title}</h2>
      <p style={{ color: 'var(--text-muted)', fontSize: 16 }}>功能开发中，敬请期待...</p>
    </motion.div>
  );
}
