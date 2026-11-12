import { useCallback, useState } from 'react';
import { Check } from 'lucide-react';

import { ToastContext } from './toast-context';

const DURATION_MS = 4000;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const toast = useCallback((message) => {
    const id = crypto.randomUUID();
    setToasts((current) => [...current, { id, message }]);
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), DURATION_MS);
  }, []);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed right-6 bottom-6 z-50 flex flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            className="flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-3 text-base text-ink shadow-sm"
          >
            <Check size={16} strokeWidth={1.5} aria-hidden="true" className="text-settled" />
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
