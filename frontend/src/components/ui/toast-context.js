import { createContext, useContext } from 'react';

export const ToastContext = createContext(null);

/** `toast("Mandate v1 signed.")` — confirmations only; errors that need action stay inline. */
export function useToast() {
  const toast = useContext(ToastContext);
  if (!toast) throw new Error('useToast must be used inside <ToastProvider>');
  return toast;
}
