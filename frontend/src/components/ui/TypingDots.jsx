import { cn } from '../../lib/cn';

/** Three dots that grow and shrink together while a reply is in progress. */
export function TypingDots({ className }) {
  return (
    <span
      role="status"
      aria-label="Replying"
      className={cn('inline-flex items-center gap-1.5', className)}
    >
      <span className="typing-dot" />
      <span className="typing-dot" />
      <span className="typing-dot" />
    </span>
  );
}
