import { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';

import { api } from '../../lib/api';
import { cn } from '../../lib/cn';

export function WorkSearch() {
  const [text, setText] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const box = useRef(null);
  const listId = useId();

  useEffect(() => {
    const handle = setTimeout(() => setDebounced(text.trim()), 300);
    return () => clearTimeout(handle);
  }, [text]);

  const results = useQuery({
    queryKey: ['search', debounced],
    enabled: debounced.length >= 2,
    queryFn: async () => (await api.get('/search', { params: { q: debounced } })).data,
  });

  useEffect(() => {
    function onPointer(event) {
      if (!box.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener('pointerdown', onPointer);
    return () => document.removeEventListener('pointerdown', onPointer);
  }, []);

  const items = results.data?.items ?? [];
  const show = open && debounced.length >= 2;
  const engine = results.data?.engine;

  return (
    <div ref={box} className="relative w-72 max-w-[40vw]">
      <input
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') setOpen(false);
        }}
        placeholder="Search contracts and workers"
        aria-label="Search contracts and workers"
        aria-expanded={show}
        aria-controls={listId}
        role="combobox"
        className="h-9 w-full rounded-md border border-line bg-surface px-3 text-sm placeholder:text-ink-muted focus:border-brand focus:outline-none"
      />
      {show && (
        <div
          id={listId}
          role="listbox"
          className="absolute top-10 right-0 z-30 w-[22rem] max-w-[80vw] overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
        >
          {results.isFetching && items.length === 0 && (
            <p className="px-3 py-2 text-sm text-ink-muted">Searching…</p>
          )}
          {!results.isFetching && items.length === 0 && (
            <p className="px-3 py-2 text-sm text-ink-muted">Nothing matches.</p>
          )}
          <ul>
            {items.map((item) => (
              <li key={`${item.kind}-${item.id}`}>
                <Link
                  to={item.href}
                  role="option"
                  onClick={() => setOpen(false)}
                  className={cn(
                    'block px-3 py-2 hover:bg-wash',
                    item.kind === 'contract' ? 'border-l-2 border-brand' : 'border-l-2 border-line',
                  )}
                >
                  <span className="block truncate text-sm font-medium">{item.title}</span>
                  <span className="block truncate text-xs text-ink-muted">{item.subtitle}</span>
                </Link>
              </li>
            ))}
          </ul>
          {engine && (
            <p className="border-t border-line px-3 py-1.5 text-xs text-ink-muted">
              {engine === 'elasticsearch'
                ? 'Ranked by Elasticsearch'
                : 'Matched in Covenant. Elasticsearch ranks this search when the cluster is up.'}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
