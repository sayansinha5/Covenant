import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowRight, ChevronDown, ChevronUp, Plus, Search, Star, X } from 'lucide-react';

import { Alert } from '../components/ui/Alert';
import { Badge } from '../components/ui/Badge';
import { Checkbox, Select } from '../components/ui/Field';
import { Modal } from '../components/ui/Modal';
import { Spinner } from '../components/ui/Spinner';
import { labelOf } from '../lib/admin';
import { problemOf } from '../lib/api';
import { cn } from '../lib/cn';
import { formatDateTime, formatMoney } from '../lib/format';
import { toCents } from '../lib/money';
import { useMarketplace, useWorker } from '../lib/queries';

const CATEGORIES = [
  { value: 'translation', label: 'Translation' },
  { value: 'catalog_data', label: 'Catalogue data' },
  { value: 'copywriting', label: 'Copywriting' },
  { value: 'design', label: 'Design' },
];
const KINDS = [
  { value: 'agent', label: 'Agents' },
  { value: 'human', label: 'People' },
];
const PRICE_MAX = 500;
const REPUTATION_MAX = 100;
const SORTS = [
  { value: 'reputation', label: 'Highest reputation' },
  { value: 'price-asc', label: 'Price: low to high' },
  { value: 'price-desc', label: 'Price: high to low' },
  { value: 'name', label: 'Name' },
];

function priceCents(amount) {
  const value = String(amount ?? '');
  if (!/^\d+(\.\d{1,2})?$/.test(value)) return 0n;
  return toCents(value);
}

function matchesQuery(worker, query) {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const skills = (worker.skills ?? []).map((skill) => skill.name).join(' ');
  const haystack = [
    worker.display_name,
    worker.org_name,
    worker.description,
    worker.kind,
    ...(worker.categories ?? []).flatMap((value) => [labelOf(value), categoryLabel(value)]),
    skills,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return haystack.includes(needle);
}

function categoryLabel(value) {
  return CATEGORIES.find((item) => item.value === value)?.label ?? labelOf(value);
}

function initials(name) {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
}

function WorkerCard({ worker, onOpen, index }) {
  return (
    <article
      className="rise-in flex items-stretch rounded-lg border border-line bg-surface shadow-sm transition-[border-color,box-shadow] duration-300 ease-fluid hover:border-brand/35"
      style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}
    >
      <button
        type="button"
        onClick={() => onOpen(worker.id)}
        className="flex min-w-0 flex-1 items-center gap-4 p-4 text-left"
      >
        <span
          aria-hidden="true"
          className="grid size-14 shrink-0 place-items-center rounded-full bg-wash text-lg font-semibold text-ink"
        >
          {initials(worker.display_name)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-lg font-semibold tracking-tight">{worker.display_name}</span>
            <Badge tone={worker.kind === 'agent' ? 'info' : 'released'}>
              {labelOf(worker.kind)}
            </Badge>
            {worker.status !== 'verified' && <Badge tone="held">{labelOf(worker.status)}</Badge>}
          </span>
          <span className="mt-0.5 block truncate text-sm text-ink-muted">{worker.org_name}</span>
          {worker.categories.length > 0 && (
            <span className="mt-1 block truncate text-sm">
              {worker.categories.map(categoryLabel).join(' · ')}
            </span>
          )}
          <span className="mt-2 flex items-center gap-1 text-xs text-ink-muted">
            <Star
              size={12}
              strokeWidth={1.5}
              className="fill-accent text-accent"
              aria-hidden="true"
            />
            <span className="font-medium text-ink">{worker.reputation}</span>
            <span>
              reputation · {worker.jobs_completed} {worker.jobs_completed === 1 ? 'job' : 'jobs'}
            </span>
          </span>
        </span>
      </button>
      <div className="flex shrink-0 flex-col items-end justify-between py-4 pr-4">
        <p className="text-lg font-semibold tracking-tight tabular-nums">
          {formatMoney(worker.price, worker.currency)}
        </p>
        <Link
          to={`/assistant?worker=${worker.id}`}
          aria-label={`Hire ${worker.display_name}`}
          className="grid size-9 place-items-center rounded-full bg-brand text-surface shadow-sm transition-[transform,background-color] duration-200 ease-fluid hover:bg-brand-hover active:scale-95"
        >
          <Plus size={16} strokeWidth={1.5} aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}

function WorkerDetail({ workerId, onClose }) {
  const worker = useWorker(workerId);
  return (
    <Modal
      open={Boolean(workerId)}
      title={worker.data?.display_name ?? 'Worker'}
      onClose={onClose}
      width="lg"
    >
      {worker.isPending && <Spinner className="text-ink-muted" />}
      {worker.isError && <Alert tone="danger">{problemOf(worker.error).detail}</Alert>}
      {worker.data && (
        <div className="flex flex-col gap-4">
          <p className="text-ink-muted">
            {labelOf(worker.data.kind)} · {worker.data.org_name}
          </p>
          {worker.data.description && <p>{worker.data.description}</p>}
          <p className="text-2xl font-semibold tracking-tight tabular-nums">
            {formatMoney(worker.data.price, worker.data.currency)}
            <span className="ml-2 text-base font-normal text-ink-muted">per job</span>
          </p>
          {worker.data.categories.length > 0 && (
            <p className="text-sm">{worker.data.categories.map(categoryLabel).join(' · ')}</p>
          )}
          {worker.data.skills.length > 0 && (
            <ul className="flex flex-col gap-1 text-sm">
              {worker.data.skills.map((skill) => (
                <li key={skill.id}>
                  {skill.name}
                  <span className="text-ink-muted"> · {(skill.tags ?? []).join(', ')}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="flex items-center gap-1 text-sm text-ink-muted">
            <Star size={12} className="fill-accent text-accent" aria-hidden="true" />
            {`Reputation ${worker.data.reputation}${
              worker.data.verified_at
                ? ` · Verified ${formatDateTime(worker.data.verified_at)}`
                : ''
            }. ${
              worker.data.jobs_completed
                ? `${worker.data.jobs_completed} jobs completed.`
                : "No completed jobs yet, so there's no history to show."
            }`}
          </p>
          <Link
            to={`/assistant?worker=${worker.data.id}`}
            className="inline-flex h-9 items-center gap-2 self-start rounded-md bg-brand px-4 font-medium text-surface shadow-sm transition-colors duration-200 hover:bg-brand-hover"
          >
            Hire with assistant
            <ArrowRight size={16} strokeWidth={1.5} aria-hidden="true" />
          </Link>
        </div>
      )}
    </Modal>
  );
}

function clampNumber(raw, min, max) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function moneyParam(amount) {
  return amount.toFixed(2);
}

const CLEAR_CLASS = 'text-xs font-semibold tracking-wide text-orange-500 hover:opacity-80';

const CHOICE_CLASS = '-mx-2 items-center gap-3 rounded-md px-2 py-2.5 hover:bg-wash';

function FilterGroup({ title, active, onClear, choices = false, children }) {
  const [open, setOpen] = useState(true);
  const Icon = open ? ChevronUp : ChevronDown;
  return (
    <section>
      <div className="border-t border-line" />
      <div className="px-4 py-3">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">{title}</h3>
          {active && (
            <button type="button" onClick={onClear} className={CLEAR_CLASS}>
              CLEAR
            </button>
          )}
          <button
            type="button"
            className="ml-auto grid size-7 place-items-center rounded-md text-ink-muted hover:bg-wash hover:text-ink"
            aria-expanded={open}
            aria-label={open ? `Hide ${title}` : `Show ${title}`}
            onClick={() => setOpen((current) => !current)}
          >
            <Icon size={16} strokeWidth={1.5} aria-hidden="true" />
          </button>
        </div>
        {open && (
          <div className={cn('flex flex-col', choices ? 'mt-1 gap-0.5' : 'mt-3 gap-2.5')}>
            {children}
          </div>
        )}
      </div>
    </section>
  );
}

function BoundInput({ label, value, min, max, onChange }) {
  return (
    <input
      type="number"
      inputMode="decimal"
      aria-label={label}
      min={min}
      max={max}
      value={value}
      onChange={(event) => onChange(clampNumber(event.target.value, min, max))}
      className="h-8 w-16 rounded-md border border-line bg-surface px-1.5 text-center text-sm tabular-nums focus:border-brand focus:outline-none"
    />
  );
}

function RangeEnds({ low, high, lowLabel, highLabel, lowMax, highMin, highMax, onLow, onHigh }) {
  return (
    <div className="flex items-center">
      <BoundInput label={lowLabel} value={low} min={0} max={lowMax} onChange={onLow} />
      <span className="flex-1 text-center text-sm text-ink-muted">to</span>
      <BoundInput label={highLabel} value={high} min={highMin} max={highMax} onChange={onHigh} />
    </div>
  );
}

function PriceRange({ minPrice, maxPrice, onMin, onMax }) {
  const span = PRICE_MAX || 1;
  const low = (minPrice / span) * 100;
  const high = (maxPrice / span) * 100;
  return (
    <div className="flex flex-col gap-3">
      <div className="relative h-5 w-full">
        <div className="absolute top-1/2 right-0 left-0 h-1 -translate-y-1/2 rounded-full bg-wash" />
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-brand"
          style={{ left: `${low}%`, width: `${Math.max(high - low, 0)}%` }}
        />
        <div className="dual-range">
          <input
            type="range"
            min={0}
            max={PRICE_MAX}
            step={1}
            value={minPrice}
            aria-label="Minimum price"
            onChange={(event) => onMin(Math.min(Number(event.target.value), maxPrice))}
            style={{ zIndex: minPrice > maxPrice - span * 0.05 ? 5 : 3 }}
          />
          <input
            type="range"
            min={0}
            max={PRICE_MAX}
            step={1}
            value={maxPrice}
            aria-label="Maximum price"
            onChange={(event) => onMax(Math.max(Number(event.target.value), minPrice))}
            style={{ zIndex: 4 }}
          />
        </div>
      </div>
      <RangeEnds
        low={minPrice}
        high={maxPrice}
        lowLabel="Minimum price"
        highLabel="Maximum price"
        lowMax={maxPrice}
        highMin={minPrice}
        highMax={PRICE_MAX}
        onLow={onMin}
        onHigh={onMax}
      />
    </div>
  );
}

function ReputationRange({ value, onChange }) {
  const position = (value / REPUTATION_MAX) * 100;
  return (
    <div className="flex flex-col gap-3">
      <div className="relative h-5 w-full">
        <div className="absolute top-1/2 right-0 left-0 h-1 -translate-y-1/2 rounded-full bg-wash" />
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-brand"
          style={{ width: `${position}%` }}
        />
        <div className="dual-range">
          <input
            type="range"
            min={0}
            max={REPUTATION_MAX}
            step={1}
            value={value}
            aria-label="Minimum reputation"
            onChange={(event) => onChange(Number(event.target.value))}
          />
        </div>
      </div>
      <BoundInput
        label="Minimum reputation"
        value={value}
        min={0}
        max={REPUTATION_MAX}
        onChange={onChange}
      />
    </div>
  );
}

/** S8 and S9: verified workers, and one worker's profile. */
export function Marketplace() {
  const [categories, setCategories] = useState([]);
  const [kinds, setKinds] = useState([]);
  const [minPrice, setMinPrice] = useState(0);
  const [maxPrice, setMaxPrice] = useState(PRICE_MAX);
  const [minReputation, setMinReputation] = useState(0);
  const [verifiedOnly, setVerifiedOnly] = useState(true);
  const [params] = useSearchParams();
  const requestedWorker = params.get('worker');
  const [query, setQuery] = useState(() => params.get('q') ?? '');
  const [sort, setSort] = useState('reputation');
  const [openId, setOpenId] = useState(requestedWorker);
  const [seenWorker, setSeenWorker] = useState(requestedWorker);
  if (requestedWorker !== seenWorker) {
    setSeenWorker(requestedWorker);
    if (requestedWorker) setOpenId(requestedWorker);
  }

  function toggle(list, setList, value) {
    setList(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  }

  const filters = {
    verified_only: verifiedOnly,
    page_size: 100,
    ...(categories.length === 1 ? { category: categories[0] } : {}),
    ...(kinds.length === 1 ? { kind: kinds[0] } : {}),
    ...(minPrice > 0 ? { min_price: moneyParam(minPrice) } : {}),
    ...(maxPrice < PRICE_MAX ? { max_price: moneyParam(maxPrice) } : {}),
    ...(minReputation > 0 ? { min_reputation: minReputation } : {}),
  };
  const listed = useMarketplace(filters);
  const visible = useMemo(() => {
    const items = (listed.data?.items ?? []).filter((worker) => {
      if (!matchesQuery(worker, query)) return false;
      if (
        categories.length > 0 &&
        !categories.some((category) => worker.categories.includes(category))
      ) {
        return false;
      }
      if (kinds.length > 0 && !kinds.includes(worker.kind)) return false;
      return true;
    });
    const copy = [...items];
    if (sort === 'price-asc') {
      copy.sort((a, b) => Number(priceCents(a.price) - priceCents(b.price)));
    } else if (sort === 'price-desc') {
      copy.sort((a, b) => Number(priceCents(b.price) - priceCents(a.price)));
    } else if (sort === 'name') {
      copy.sort((a, b) => a.display_name.localeCompare(b.display_name));
    } else {
      copy.sort(
        (a, b) => b.reputation - a.reputation || a.display_name.localeCompare(b.display_name),
      );
    }
    return copy;
  }, [listed.data, query, sort, categories, kinds]);

  const priceActive = minPrice > 0 || maxPrice < PRICE_MAX;
  const reputationActive = minReputation > 0;
  const filtersActive =
    query.trim() !== '' ||
    categories.length > 0 ||
    kinds.length > 0 ||
    priceActive ||
    reputationActive ||
    !verifiedOnly;

  function clearFilters() {
    setQuery('');
    setCategories([]);
    setKinds([]);
    setMinPrice(0);
    setMaxPrice(PRICE_MAX);
    setMinReputation(0);
    setVerifiedOnly(true);
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="max-w-xl">
        <h2 className="text-3xl font-semibold tracking-tight">Find a worker</h2>
      </header>

      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        <aside className="sticky top-20 z-10 flex max-h-[calc(100vh-6rem)] w-full shrink-0 flex-col self-start overflow-x-hidden overflow-y-auto rounded-lg border border-line bg-surface shadow-sm lg:w-72">
          <div className="flex items-center justify-between px-4 pt-4">
            <h2 className="text-sm font-semibold">Filters</h2>
            {filtersActive && (
              <button type="button" onClick={clearFilters} className={CLEAR_CLASS}>
                CLEAR ALL
              </button>
            )}
          </div>
          <div className="px-4 pt-3 pb-3">
            <div className="relative">
              <Search
                size={16}
                strokeWidth={1.5}
                aria-hidden="true"
                className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-muted"
              />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Name, studio, or skill"
                aria-label="Search workers"
                className="h-9 w-full rounded-md border border-line bg-surface pr-9 pl-9 text-sm placeholder:text-ink-muted focus:border-brand focus:outline-none"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  aria-label="Clear search"
                  className="absolute top-1/2 right-1 grid size-7 -translate-y-1/2 place-items-center rounded-md text-ink-muted hover:bg-wash hover:text-ink"
                >
                  <X size={14} strokeWidth={1.5} aria-hidden="true" />
                </button>
              )}
            </div>
          </div>

          <FilterGroup
            title="Category"
            active={categories.length > 0}
            onClear={() => setCategories([])}
            choices
          >
            {CATEGORIES.map((item) => (
              <Checkbox
                key={item.value}
                id={`category-${item.value}`}
                label={item.label}
                className={CHOICE_CLASS}
                checked={categories.includes(item.value)}
                onChange={() => toggle(categories, setCategories, item.value)}
              />
            ))}
          </FilterGroup>

          <FilterGroup title="Type" active={kinds.length > 0} onClear={() => setKinds([])} choices>
            {KINDS.map((item) => (
              <Checkbox
                key={item.value}
                id={`kind-${item.value}`}
                label={item.label}
                className={CHOICE_CLASS}
                checked={kinds.includes(item.value)}
                onChange={() => toggle(kinds, setKinds, item.value)}
              />
            ))}
          </FilterGroup>

          <FilterGroup
            title="Price"
            active={priceActive}
            onClear={() => {
              setMinPrice(0);
              setMaxPrice(PRICE_MAX);
            }}
          >
            <PriceRange
              minPrice={minPrice}
              maxPrice={maxPrice}
              onMin={setMinPrice}
              onMax={setMaxPrice}
            />
          </FilterGroup>

          <FilterGroup
            title="Reputation"
            active={reputationActive}
            onClear={() => setMinReputation(0)}
          >
            <ReputationRange value={minReputation} onChange={setMinReputation} />
          </FilterGroup>

          <FilterGroup
            title="Verified"
            active={verifiedOnly}
            onClear={() => setVerifiedOnly(false)}
          >
            <Checkbox
              id="verified-only"
              label="Verified only"
              checked={verifiedOnly}
              onChange={(event) => setVerifiedOnly(event.target.checked)}
            />
          </FilterGroup>
        </aside>

        <div className="@container min-w-0 flex-1">
          <div className="mb-4 flex items-center justify-between gap-3">
            <p className="text-sm text-ink-muted">
              {listed.isPending
                ? 'Loading workers'
                : visible.length === 1
                  ? '1 worker'
                  : `${visible.length} workers`}
            </p>
            <div className="w-48">
              <Select
                aria-label="Sort"
                options={SORTS}
                value={sort}
                onChange={(event) => setSort(event.target.value)}
              />
            </div>
          </div>
          {listed.isPending && <Spinner className="text-ink-muted" />}
          {listed.isError && <Alert tone="danger">{problemOf(listed.error).detail}</Alert>}
          {listed.data && visible.length === 0 && (
            <p className="rounded-lg border border-dashed border-line bg-surface p-6 text-ink-muted">
              {query ? `No workers match "${query}".` : 'No workers match these filters.'}
            </p>
          )}
          {listed.data && visible.length > 0 && (
            <div
              className={cn(
                'grid grid-cols-1 gap-4 @min-[640px]:grid-cols-2',
                listed.isFetching && 'opacity-80 transition-opacity',
              )}
            >
              {visible.map((worker, index) => (
                <WorkerCard key={worker.id} worker={worker} index={index} onOpen={setOpenId} />
              ))}
            </div>
          )}
        </div>
      </div>
      <WorkerDetail workerId={openId} onClose={() => setOpenId(null)} />
    </div>
  );
}
