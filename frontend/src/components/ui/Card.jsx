import { cn } from '../../lib/cn';

export function Card({ as: Element = 'div', className, children, ...props }) {
  return (
    <Element
      className={cn('rounded-lg border border-line bg-surface shadow-sm', className)}
      {...props}
    >
      {children}
    </Element>
  );
}
