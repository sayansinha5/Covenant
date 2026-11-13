import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Square, Star } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';

import { ContractReview } from '../components/contracts/ContractReview';
import { Alert } from '../components/ui/Alert';
import { Avatar } from '../components/ui/Avatar';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { TypingDots } from '../components/ui/TypingDots';
import { labelOf } from '../lib/admin';
import { api, problemOf } from '../lib/api';
import { cn } from '../lib/cn';
import { formatMoney } from '../lib/format';
import { readCatalogBrief } from '../lib/catalog';
import { useContract } from '../lib/queries';
import { takeFrames } from '../lib/stream';

const CHAT_TEXT_WIDTH = 'w-fit max-w-[92%] md:max-w-[46%]';
const SUGGESTION_CLASS =
  'rounded-md border border-line bg-surface px-4 py-2 text-left text-sm shadow-sm transition-[border-color,background-color] duration-200 ease-fluid hover:border-brand hover:bg-brand-subtle';

const SUGGESTIONS = [
  'Wanted a worker for a product page for translation under $50',
  'Translate a listing into German, budget for translation around $40',
  'Find a designer for a product page under $80',
  'Shortlist copywriters with reputation above 50',
  'List me all the workers for every category',
];

export function Assistant() {
  const [params] = useSearchParams();
  const worker = params.get('worker');
  const fromCatalog = params.get('from') === 'catalog';
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState('');
  const [text, setText] = useState(() => {
    if (worker) return `Hire worker ${worker}. Ask what I need, then draft the contract.`;
    if (fromCatalog) return readCatalogBrief();
    return '';
  });
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [openId, setOpenId] = useState('');
  const review = useContract(openId);
  const composer = useRef(null);
  const scroller = useRef(null);
  const follow = useRef(true);
  const abortRef = useRef(null);
  const requestRef = useRef(0);
  const [seenWorker, setSeenWorker] = useState(worker);
  if (worker !== seenWorker) {
    setSeenWorker(worker);
    if (worker) {
      setText(`Hire worker ${worker}. Ask what I need, then draft the contract.`);
    }
  }
  const [seenCatalog, setSeenCatalog] = useState(fromCatalog);
  if (fromCatalog !== seenCatalog) {
    setSeenCatalog(fromCatalog);
    if (fromCatalog && !worker) setText(readCatalogBrief());
  }

  useEffect(() => {
    const field = composer.current;
    if (!field) return;
    field.style.height = 'auto';
    field.style.height = `${Math.min(field.scrollHeight, 160)}px`;
  }, [text]);

  useLayoutEffect(() => {
    const pane = scroller.current;
    if (!pane || messages.length === 0 || !follow.current) return;
    pane.scrollTop = pane.scrollHeight;
  }, [messages, text]);

  function onThreadScroll() {
    const pane = scroller.current;
    if (!pane) return;
    follow.current = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 48;
  }

  async function ensureConversation() {
    if (conversationId) return conversationId;
    const created = await api.post('/assistant/conversations');
    setConversationId(created.data.id);
    return created.data.id;
  }

  function patchMessage(id, updater) {
    setMessages((current) =>
      current.map((message) => (message.id === id ? updater(message) : message)),
    );
  }

  function stop() {
    requestRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
    setMessages((current) =>
      current.flatMap((item) => {
        if (item.role !== 'assistant' || !item.pending) return [item];
        const bare = !item.text && item.cards.length === 0 && item.steps.length === 0;
        return bare ? [] : [{ ...item, pending: false }];
      }),
    );
  }

  async function send(event) {
    event.preventDefault();
    const message = text.trim();
    if (!message || busy) return;
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();
    const controller = new AbortController();
    abortRef.current = controller;
    follow.current = true;
    setMessages((current) => [
      ...current,
      { id: userId, role: 'user', text: message },
      { id: assistantId, role: 'assistant', text: '', cards: [], steps: [], pending: true },
    ]);
    setText('');
    setBusy(true);
    setError('');
    const stillMine = () => requestRef.current === requestId;
    try {
      const id = await ensureConversation();
      if (!stillMine()) return;
      let seen = '';
      let pending = '';
      await api.post(
        `/assistant/conversations/${id}/messages`,
        { text: message },
        {
          responseType: 'text',
          timeout: 120000,
          signal: controller.signal,
          onDownloadProgress: (progress) => {
            if (!stillMine()) return;
            const soFar = progress.event?.target?.responseText ?? '';
            pending += soFar.slice(seen.length);
            seen = soFar;
            const parsed = takeFrames(pending);
            pending = parsed.rest;
            for (const frame of parsed.frames) {
              patchMessage(assistantId, (current) => applyFrame(frame, current));
            }
          },
        },
      );
      if (!stillMine()) return;
      await queryClient.invalidateQueries({ queryKey: ['contract'] });
    } catch (err) {
      if (!stillMine() || err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return;
      const detail = problemOf(err).detail;
      setError(detail);
      patchMessage(assistantId, (current) => ({ ...current, error: detail }));
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      if (stillMine()) {
        patchMessage(assistantId, (current) => ({ ...current, pending: false }));
        setBusy(false);
      }
    }
  }

  function onComposerKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (!busy) event.currentTarget.form?.requestSubmit();
    }
  }

  function fillComposer(next) {
    setText(next);
    composer.current?.focus();
  }

  function pickWorker(worker) {
    fillComposer(
      `Hire ${worker.name}. worker_id: ${worker.id}. Ask what I need, then draft the contract.`,
    );
  }

  function onComposerChange(event) {
    const field = event.currentTarget;
    const pinned = follow.current;
    setText(field.value);
    field.style.height = 'auto';
    field.style.height = `${Math.min(field.scrollHeight, 160)}px`;
    const pane = scroller.current;
    if (!pinned || !pane) return;
    pane.scrollTop = pane.scrollHeight;
    follow.current = true;
  }

  const empty = messages.length === 0;

  const composerProps = {
    value: text,
    busy,
    inputRef: composer,
    onChange: onComposerChange,
    onKeyDown: onComposerKeyDown,
    onSubmit: (event) => void send(event),
    onStop: stop,
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scroller} onScroll={onThreadScroll} className="min-h-0 flex-1 overflow-y-auto">
        {empty ? (
          <div className="flex min-h-full items-center px-6 py-8">
            <div className="rise-in mx-auto flex w-full max-w-[640px] -translate-y-28 flex-col">
              <p className="text-xs font-semibold tracking-[0.16em] text-ink-muted uppercase">
                Buyer agent
              </p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight">
                Describe the job. You still fund it.
              </h2>
              <p className="mt-3 text-ink-muted">
                The assistant can shortlist workers and draft a contract. Nothing is held until you
                review that draft and pay.
              </p>
              <div className="mt-6">
                <Composer {...composerProps} tall />
              </div>
              <div className="mt-4 flex flex-col items-start gap-2">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => fillComposer(suggestion)}
                    className={SUGGESTION_CLASS}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="mx-auto flex w-full max-w-[760px] flex-col gap-5 px-6 pt-8 pb-6">
            {messages.map((message, index) =>
              message.role === 'user' ? (
                <p
                  key={message.id}
                  className={cn(
                    'rise-in self-end rounded-lg bg-gray-100 px-4 py-3 text-ink',
                    CHAT_TEXT_WIDTH,
                  )}
                >
                  {message.text}
                </p>
              ) : (
                <AssistantTurn
                  key={message.id}
                  message={message}
                  onOpen={setOpenId}
                  onHire={pickWorker}
                  suggestions={
                    index === messages.length - 1 && !message.pending ? followUps(message) : []
                  }
                  onSuggest={fillComposer}
                />
              ),
            )}
            {error && messages.every((message) => !message.error) && (
              <Alert tone="danger">{error}</Alert>
            )}
          </div>
        )}
      </div>

      {!empty && (
        <div className="shrink-0 bg-canvas px-6 pt-2 pb-4">
          <div className="mx-auto w-full max-w-[760px]">
            <Composer {...composerProps} />
          </div>
        </div>
      )}

      <ContractReview
        contract={review.data}
        open={Boolean(openId && review.data)}
        onClose={() => setOpenId('')}
        canFund
      />
    </div>
  );
}

function Composer({ value, busy, tall = false, inputRef, onChange, onKeyDown, onSubmit, onStop }) {
  const showAction = busy || value.trim().length > 0;
  return (
    <form onSubmit={onSubmit}>
      <div
        className={cn(
          'relative rounded-md bg-surface shadow-sm transition-colors duration-200',
          busy
            ? 'composer-orbit overflow-hidden p-0.5'
            : 'border border-line focus-within:border-brand',
        )}
      >
        <textarea
          ref={inputRef}
          rows={tall ? 4 : 1}
          value={value}
          aria-label="Describe the job"
          placeholder="List me all the workers for every category"
          onChange={onChange}
          onKeyDown={onKeyDown}
          className={cn(
            'relative z-10 block max-h-40 w-full resize-none rounded-md bg-surface py-3 pl-4 text-base',
            tall ? 'min-h-[104px]' : 'min-h-12',
            'placeholder:text-ink-muted focus:outline-none',
            showAction ? 'pr-14' : 'pr-4',
          )}
        />
        {showAction && (
          <button
            type={busy ? 'button' : 'submit'}
            onClick={busy ? onStop : undefined}
            aria-label={busy ? 'Stop' : 'Send'}
            className="absolute right-2 bottom-2 z-10 grid size-8 place-items-center rounded-md bg-brand text-surface transition-[transform,background-color] duration-200 ease-fluid hover:bg-brand-hover active:scale-95"
          >
            {busy ? (
              <Square size={12} strokeWidth={2.5} className="fill-current" aria-hidden="true" />
            ) : (
              <ArrowRight size={16} strokeWidth={1.5} aria-hidden="true" />
            )}
          </button>
        )}
      </div>
    </form>
  );
}

function applyFrame(frame, message) {
  if (frame.event === 'token') {
    return { ...message, text: message.text + (frame.data.text ?? '') };
  }
  if (frame.event === 'card') {
    return { ...message, cards: [...message.cards, frame.data] };
  }
  if (frame.event === 'step') {
    return { ...message, steps: [...message.steps, frame.data] };
  }
  if (frame.event === 'error') {
    return { ...message, error: frame.data.message ?? 'Something went wrong.' };
  }
  return message;
}

function stripRoster(text) {
  return text
    .split('\n')
    .filter((line) => !/^\s*([-*]|\d+\.)\s+/.test(line))
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function splitNarrative(text) {
  const body = text.trim();
  if (!body) return { before: '', after: '' };
  const paragraphs = body
    .split(/\n\s*\n/)
    .map((part) => part.trim())
    .filter(Boolean);
  const last = paragraphs[paragraphs.length - 1];
  if (paragraphs.length > 1 && last.endsWith('?')) {
    return { before: paragraphs.slice(0, -1).join('\n\n'), after: last };
  }
  const sentences = last.split(/(?<=[.!])\s+(?=[A-Z])/);
  if (sentences.length > 1 && sentences[sentences.length - 1].endsWith('?')) {
    const question = sentences.pop();
    const head = [...paragraphs.slice(0, -1), sentences.join(' ')].filter(Boolean).join('\n\n');
    return { before: head, after: question };
  }
  return { before: paragraphs.join('\n\n'), after: '' };
}

function narrativeParts(message, workers) {
  const cleaned = workers.length > 0 ? stripRoster(message.text) : message.text.trim();
  const parts = splitNarrative(cleaned);
  if (message.pending || workers.length === 0) return parts;
  const categories = new Set(workers.flatMap((worker) => worker.categories ?? []));
  return {
    before:
      parts.before ||
      (categories.size > 1
        ? 'Here are the available workers in different categories:'
        : 'Here are the available workers:'),
    after: parts.after || 'Would you like to proceed with drafting a contract?',
  };
}

const CATEGORY_LABELS = {
  translation: 'Translation',
  catalog_data: 'Catalogue data',
  copywriting: 'Copywriting',
  design: 'Design',
};

function categoryLabel(value) {
  return CATEGORY_LABELS[value] ?? labelOf(value);
}

function workerCountLabel(count) {
  return `${count} ${count === 1 ? 'worker' : 'workers'}`;
}

function stepLabels(steps, workerCount) {
  const labels = [];
  if (steps.some((step) => step.name === 'search_workers')) {
    labels.push(`Search workers: ${workerCountLabel(workerCount)}`);
  }
  const seen = new Set();
  for (const step of steps) {
    if (step.name === 'search_workers' || seen.has(step.name)) continue;
    seen.add(step.name);
    labels.push(`${labelOf(step.name)}: ${step.status}`);
  }
  return labels;
}

function followUps(message) {
  const workers = uniqueWorkers(message.cards);
  const contract = message.cards.find((card) => card.contract_id);
  if (contract) {
    return [
      `Revise ${contract.number} and lower the budget.`,
      'What happens after I agree and fund?',
      'Show me another worker for this job.',
    ];
  }
  if (workers.length === 1) {
    return [
      `Draft a contract with ${workers[0].name}.`,
      `Tell me more about ${workers[0].name}.`,
      'Show me other workers in this category.',
    ];
  }
  if (workers.length > 1) {
    return [
      `Draft a contract with ${workers[0].name}.`,
      'Which of these is the best fit?',
      'Show me only people, not agents.',
    ];
  }
  if (message.error) {
    return ['Try that again.', 'Find a designer for a product page under $80.'];
  }
  return [
    'Find a designer for a product page under $80.',
    'Shortlist copywriters with reputation above 50.',
    'What can you draft before any money is held?',
  ];
}

function AssistantTurn({ message, onOpen, onHire, suggestions = [], onSuggest }) {
  const workers = uniqueWorkers(message.cards);
  const { before, after } = narrativeParts(message, workers);
  const labels = stepLabels(message.steps, workers.length);
  const others = message.cards.filter((card) => !isWorkerCard(card));
  return (
    <div className="rise-in flex w-full flex-col gap-3 self-start">
      {before && <ChatText>{before}</ChatText>}
      {labels.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {labels.map((label) => (
            <li key={label}>
              <Badge tone="info">{label}</Badge>
            </li>
          ))}
        </ul>
      )}
      {workers.length > 0 && <WorkerResults workers={workers} onHire={onHire} />}
      {others.map((card, index) => (
        <WorkerOrProposal key={index} card={card} onOpen={onOpen} />
      ))}
      {after && <ChatText>{after}</ChatText>}
      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => onSuggest(suggestion)}
              className={SUGGESTION_CLASS}
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
      {message.pending && <TypingDots />}
      {message.error && <Alert tone="danger">{message.error}</Alert>}
    </div>
  );
}

function ChatText({ children }) {
  return <p className={cn('whitespace-pre-wrap text-ink', CHAT_TEXT_WIDTH)}>{children}</p>;
}

function isWorkerCard(card) {
  return card.type === 'shortlist' || card.type === 'worker';
}

function workersOf(card) {
  if (card.type === 'shortlist') return card.workers ?? [];
  if (card.type === 'worker' && card.id) return [card];
  return null;
}

function uniqueWorkers(cards) {
  const seen = new Set();
  const workers = [];
  for (const card of cards) {
    for (const worker of workersOf(card) ?? []) {
      if (!worker.id || seen.has(worker.id)) continue;
      seen.add(worker.id);
      workers.push(worker);
    }
  }
  return workers;
}

function WorkerResults({ workers, onHire }) {
  if (workers.length === 1) return <WorkerCard worker={workers[0]} onHire={onHire} />;
  return <WorkerTable workers={workers} onHire={onHire} />;
}

function WorkerOrProposal({ card, onOpen }) {
  if (card.contract_id) {
    return (
      <Card className="flex flex-col gap-2 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-xs font-semibold tracking-[0.14em] text-ink-muted uppercase">
            Contract draft
          </p>
          {card.state && <Badge tone="held">{labelOf(card.state)}</Badge>}
        </div>
        <p className="font-semibold">
          {card.number} {card.title}
        </p>
        {card.worker_name && <p className="text-sm text-ink-muted">{card.worker_name}</p>}
        <p className="text-lg font-semibold tracking-tight tabular-nums">
          {formatMoney(card.amount, card.currency)}
        </p>
        <Button
          className="self-start"
          size="sm"
          variant="secondary"
          onClick={() => onOpen(card.contract_id)}
        >
          Review contract
        </Button>
      </Card>
    );
  }
  if (card.message) return <Alert tone="danger">{card.message}</Alert>;
  return null;
}

function WorkerCard({ worker, onHire }) {
  const jobs = worker.jobs_completed ?? 0;
  return (
    <Card className="flex items-center gap-3 p-3">
      <Avatar name={worker.name} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold tracking-tight">{worker.name}</span>
          <Badge tone={worker.kind === 'agent' ? 'info' : 'released'}>{labelOf(worker.kind)}</Badge>
        </div>
        {worker.categories?.length > 0 && (
          <p className="mt-0.5 truncate text-sm text-ink-muted">
            {worker.categories.map((category) => categoryLabel(category)).join(' · ')}
          </p>
        )}
        <p className="mt-1.5 flex items-center gap-1 text-xs text-ink-muted">
          <Star
            size={12}
            strokeWidth={1.5}
            className="fill-accent text-accent"
            aria-hidden="true"
          />
          <span className="font-medium text-ink">{worker.reputation}</span>
          <span>
            reputation · {jobs} {jobs === 1 ? 'job' : 'jobs'}
          </span>
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-2">
        <p className="font-semibold tracking-tight tabular-nums">
          {formatMoney(worker.price, worker.currency)}
        </p>
        <Button size="sm" onClick={() => onHire(worker)}>
          Hire
        </Button>
      </div>
    </Card>
  );
}

function WorkerTable({ workers, onHire }) {
  return (
    <Card className="overflow-x-auto p-0">
      <table className="w-full min-w-[520px] border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-line text-xs text-ink-muted">
            <th className="px-3 py-2 font-medium">Worker</th>
            <th className="px-3 py-2 font-medium">Type</th>
            <th className="px-3 py-2 font-medium">Category</th>
            <th className="px-3 py-2 font-medium">Reputation</th>
            <th className="px-3 py-2 font-medium">Price</th>
            <th className="px-3 py-2 font-medium">
              <span className="sr-only">Hire</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {workers.map((worker) => (
            <tr key={worker.id} className="border-b border-line last:border-b-0">
              <td className="px-3 py-2">
                <span className="flex items-center gap-2 font-medium">
                  <Avatar name={worker.name} size="sm" />
                  {worker.name}
                </span>
              </td>
              <td className="px-3 py-2">
                <Badge tone={worker.kind === 'agent' ? 'info' : 'released'}>
                  {labelOf(worker.kind)}
                </Badge>
              </td>
              <td className="px-3 py-2 text-ink-muted">
                {(worker.categories ?? []).map((category) => categoryLabel(category)).join(', ')}
              </td>
              <td className="px-3 py-2 tabular-nums">{worker.reputation}</td>
              <td className="px-3 py-2 font-medium tabular-nums">
                {formatMoney(worker.price, worker.currency)}
              </td>
              <td className="px-3 py-2 text-right">
                <Button size="sm" onClick={() => onHire(worker)}>
                  Hire
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
