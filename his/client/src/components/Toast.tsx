import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface ToastItem {
  id: number;
  message: string;
  type: 'success' | 'error' | 'info' | 'warning';
}

let toastId = 0;
const listeners: Set<(toast: ToastItem) => void> = new Set();

export function showToast(message: string, type: 'success' | 'error' | 'info' | 'warning' = 'info') {
  const toast: ToastItem = { id: ++toastId, message, type };
  listeners.forEach((fn) => fn(toast));
}

const COLORS: Record<string, string> = {
  success: 'linear-gradient(135deg, #5CB85C, #3D8B3D)',
  error: 'linear-gradient(135deg, #DC2626, #B91C1C)',
  info: 'linear-gradient(135deg, #4A90D9, #2D6DB5)',
  warning: 'linear-gradient(135deg, #F0AD4E, #D97706)',
};

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const addToast = useCallback((toast: ToastItem) => {
    setToasts((prev) => [...prev, toast]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== toast.id));
    }, 3500);
  }, []);

  useEffect(() => {
    listeners.add(addToast);
    return () => { listeners.delete(addToast); };
  }, [addToast]);

  return (
    <div style={{ position: 'fixed', top: 120, left: '50%', transform: 'translateX(-50%)', zIndex: 9999, display: 'flex', flexDirection: 'column', gap: 10, pointerEvents: 'none' }}>
      <AnimatePresence>
        {toasts.map((toast) => (
          <motion.div
            key={toast.id}
            initial={{ opacity: 0, y: -30, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.9 }}
            transition={{ type: 'spring', damping: 20, stiffness: 300 }}
            style={{
              background: COLORS[toast.type],
              color: '#fff',
              padding: '14px 28px',
              borderRadius: 50,
              fontSize: 15,
              fontWeight: 600,
              boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
              pointerEvents: 'auto',
              display: 'flex',
              alignItems: 'center',
              whiteSpace: 'nowrap',
            }}
          >
            {toast.message}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}
