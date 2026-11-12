import { cn } from '../../lib/cn';

export function Wordmark({ compact = false, className }) {
  return (
    <span
      className={cn(
        'inline-flex items-center text-lg font-semibold tracking-tight text-ink',
        compact ? 'justify-center' : 'gap-2',
        className,
      )}
    >
      <span aria-hidden="true" className="size-4 shrink-0 rounded-full bg-brand" />
      <span className={cn(compact && 'sr-only')}>Covenant</span>
    </span>
  );
}
