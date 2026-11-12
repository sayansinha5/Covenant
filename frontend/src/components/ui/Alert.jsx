import { CircleAlert, Info } from 'lucide-react';

import { cn } from '../../lib/cn';

const TONES = {
  info: { className: 'bg-info-bg text-info', icon: Info, role: 'status' },
  held: { className: 'bg-held-bg text-held', icon: Info, role: 'status' },
  danger: { className: 'bg-danger-bg text-danger', icon: CircleAlert, role: 'alert' },
};

export function Alert({ tone = 'info', className, children }) {
  const { className: toneClass, icon: Icon, role } = TONES[tone];
  return (
    <div
      role={role}
      className={cn('flex gap-2 rounded-md px-3 py-2 text-sm', toneClass, className)}
    >
      <Icon size={16} strokeWidth={1.5} aria-hidden="true" className="mt-px shrink-0" />
      <div>{children}</div>
    </div>
  );
}
