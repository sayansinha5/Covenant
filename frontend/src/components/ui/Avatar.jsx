import { cn } from '../../lib/cn';

const SIZES = {
  sm: 'size-9 text-sm',
  md: 'size-11 text-base',
};

function initials(name) {
  return String(name ?? '')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
}

/** A round mark of a person's initials. The name stays in the surrounding text. */
export function Avatar({ name, size = 'md', className }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'grid shrink-0 place-items-center rounded-full bg-brand-subtle font-semibold text-brand',
        SIZES[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  );
}
