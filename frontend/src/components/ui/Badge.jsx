import { cn } from '../../lib/cn';

const TONES = {
  held: 'bg-held-bg text-held',
  settled: 'bg-settled-bg text-settled',
  released: 'bg-released-bg text-released',
  danger: 'bg-danger-bg text-danger',
  info: 'bg-info-bg text-info',
};

/** A status pill. Always pass a text label: colour is never the only signal. */
export function Badge({ tone = 'released', className, children }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
