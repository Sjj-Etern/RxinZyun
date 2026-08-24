import { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';

export interface GlassSelectOption {
  value: string;
  label: string;
}

interface Props {
  value: string;
  options: GlassSelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
}

export default function GlassSelect({ value, options, onChange, placeholder = '请选择' }: Props) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0, width: 0 });
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const selected = options.find((option) => option.value === value);

  const calcPos = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setPos({ top: rect.bottom + 4, left: rect.left, width: rect.width });
  }, []);

  const openDropdown = useCallback(() => {
    calcPos();
    setOpen(true);
  }, [calcPos]);

  // Close on outside pointer-down — include portal menu in hit test
  useEffect(() => {
    const close = (event: PointerEvent) => {
      const target = event.target as Node;
      const insideRoot = rootRef.current?.contains(target);
      const insideMenu = menuRef.current?.contains(target);
      if (!insideRoot && !insideMenu) {
        setOpen(false);
      }
    };

    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, []);

  // Reposition on scroll / resize while open
  useEffect(() => {
    if (!open) return;
    const handle = () => calcPos();
    window.addEventListener('resize', handle);
    window.addEventListener('scroll', handle, true);
    return () => {
      window.removeEventListener('resize', handle);
      window.removeEventListener('scroll', handle, true);
    };
  }, [open, calcPos]);

  return (
    <div className={`glass-select ${open ? 'glass-select--open' : ''}`} ref={rootRef}>
      <button className="glass-select-trigger" type="button" ref={triggerRef} onClick={() => (open ? setOpen(false) : openDropdown())}>
        <span>{selected?.label || placeholder}</span>
        <span className="glass-select-arrow" aria-hidden="true" />
      </button>
      {open &&
        createPortal(
          <div
            ref={menuRef}
            className="glass-select-menu"
            role="listbox"
            style={{ position: 'fixed', top: pos.top, left: pos.left, width: pos.width, zIndex: 9999 }}
          >
            {options.map((option) => (
              <button
                className={`glass-select-option ${option.value === value ? 'glass-select-option--active' : ''}`}
                key={option.value}
                type="button"
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                role="option"
                aria-selected={option.value === value}
              >
                {option.label}
              </button>
            ))}
          </div>,
          document.body
        )}
    </div>
  );
}
