import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

import { api } from '../../lib/api';
import { NOTIFICATIONS_KEY, useNotifications } from '../../lib/queries';

export function Notifications() {
  const notes = useNotifications();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const items = notes.data ?? [];
  const unread = items.filter((item) => !item.read_at).length;

  async function markAll() {
    await api.post('/notifications/read-all');
    await queryClient.invalidateQueries({ queryKey: NOTIFICATIONS_KEY });
  }

  return (
    <div className="relative">
      <button
        type="button"
        className="relative rounded-md p-2 transition-colors duration-200 hover:bg-wash"
        aria-label={unread ? `${unread} unread notifications` : 'Notifications'}
        onClick={() => setOpen((value) => !value)}
      >
        <Bell size={18} />
        {unread > 0 && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-danger" />}
      </button>
      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-lg border border-line bg-surface p-3 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <span className="font-medium">Notifications</span>
            {unread > 0 && (
              <button type="button" className="text-sm text-brand" onClick={() => void markAll()}>
                Mark all read
              </button>
            )}
          </div>
          {items.length === 0 && <p className="text-sm text-ink-muted">You're up to date.</p>}
          <ul className="flex max-h-80 flex-col gap-2 overflow-auto">
            {items.map((item) => (
              <li key={item.id} className="text-sm">
                {item.link ? (
                  <Link to={item.link} onClick={() => setOpen(false)} className="font-medium">
                    {item.title}
                  </Link>
                ) : (
                  <span className="font-medium">{item.title}</span>
                )}
                <p className="text-ink-muted">{item.body}</p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
