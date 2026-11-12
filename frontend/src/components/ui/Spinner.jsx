import { LoaderCircle } from 'lucide-react';

import { cn } from '../../lib/cn';

export function Spinner({ className }) {
  return (
    <LoaderCircle
      aria-hidden="true"
      size={16}
      strokeWidth={1.5}
      className={cn('animate-spin', className)}
    />
  );
}
