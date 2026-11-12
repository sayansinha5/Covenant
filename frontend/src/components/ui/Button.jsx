import { cn } from '../../lib/cn';
import { Spinner } from './Spinner';

const VARIANTS = {
  primary: 'bg-brand text-surface shadow-sm hover:bg-brand-hover',
  secondary: 'border border-line bg-surface text-ink hover:bg-wash',
  ghost: 'text-ink-muted hover:bg-wash hover:text-ink',
  danger: 'bg-danger text-surface hover:opacity-90',
};

const SIZES = {
  md: 'h-9 px-4',
  sm: 'h-8 px-3 text-sm',
};

/** While `loading`, the button is disabled and shows `loadingText` so it can't be clicked twice. */
export function Button({
  variant = 'primary',
  size = 'md',
  type = 'button',
  loading = false,
  loadingText,
  disabled,
  className,
  children,
  ...props
}) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-md font-medium whitespace-nowrap',
        'transition-[color,background-color,transform,box-shadow] duration-200 ease-fluid',
        'active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60 disabled:active:scale-100',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {loading && <Spinner />}
      {loading && loadingText ? loadingText : children}
    </button>
  );
}
