import { useEffect, useEffectEvent, useId, useRef } from 'react';
import { X } from 'lucide-react';
import { createPortal } from 'react-dom';

import { cn } from '../../lib/cn';

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Centred dialog with a focus trap. `busy` (a money action in flight) blocks Esc and the
 * backdrop so the request can't be abandoned halfway.
 */
export function Modal({ open, title, onClose, busy = false, width = 'md', footer, children }) {
  const titleId = useId();
  const panel = useRef(null);
  const closeOnEscape = useEffectEvent(() => {
    if (!busy) onClose();
  });

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.activeElement;
    const first = panel.current?.querySelector(FOCUSABLE);
    (first ?? panel.current)?.focus();

    function onKeyDown(event) {
      if (event.key === 'Escape') {
        event.stopPropagation();
        closeOnEscape();
      }
      if (event.key !== 'Tab' || !panel.current) return;
      const focusable = [...panel.current.querySelectorAll(FOCUSABLE)];
      if (focusable.length === 0) return;
      const [head, tail] = [focusable[0], focusable.at(-1)];
      if (event.shiftKey && document.activeElement === head) {
        event.preventDefault();
        tail.focus();
      } else if (!event.shiftKey && document.activeElement === tail) {
        event.preventDefault();
        head.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      previous?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-40 flex items-center justify-center p-4">
      <div
        aria-hidden="true"
        className="absolute inset-0 bg-ink/40"
        onMouseDown={() => !busy && onClose()}
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          'relative flex max-h-[90vh] w-full flex-col rounded-lg border border-line bg-surface shadow-sm',
          width === 'lg' ? 'max-w-[840px]' : 'max-w-[560px]',
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <h2 id={titleId} className="text-lg font-semibold tracking-tight">
            {title}
          </h2>
          <button
            type="button"
            aria-label="Close"
            disabled={busy}
            onClick={() => !busy && onClose()}
            className="grid size-8 shrink-0 place-items-center rounded-md text-ink-muted transition-colors hover:bg-wash hover:text-ink disabled:cursor-not-allowed disabled:opacity-40"
          >
            <X size={16} strokeWidth={1.5} aria-hidden="true" />
          </button>
        </div>
        <div className="overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex items-center justify-end gap-2 border-t border-line px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
