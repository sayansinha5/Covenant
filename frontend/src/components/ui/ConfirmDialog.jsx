import { useEffect } from 'react';

import { Button } from './Button';

/** A small confirmation. Escape and Cancel dismiss it; only the confirm button proceeds. */
export function ConfirmDialog({
  title,
  children,
  confirmLabel = 'Remove',
  busy = false,
  onCancel,
  onConfirm,
}) {
  useEffect(() => {
    function onKey(event) {
      if (event.key === 'Escape' && !busy) onCancel();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [busy, onCancel]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-body"
        className="w-full max-w-md rounded-lg border border-line bg-surface p-5 shadow-sm"
      >
        <h2 id="confirm-title" className="text-lg font-semibold tracking-tight">
          {title}
        </h2>
        <div id="confirm-body" className="mt-2 text-sm text-ink-muted">
          {children}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel} disabled={busy} autoFocus>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={onConfirm}
            loading={busy}
            loadingText="Removing…"
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
