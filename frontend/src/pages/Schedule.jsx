import '../lib/bryntumLicense';
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { BryntumScheduler } from '@bryntum/scheduler-react-enterprise';

import '@bryntum/scheduler-enterprise/stockholm-light.css';

import { Alert } from '../components/ui/Alert';
import { Card } from '../components/ui/Card';
import { Spinner } from '../components/ui/Spinner';
import { problemOf } from '../lib/api';
import { useSchedule } from '../lib/queries';

const EVENT_COLOR = {
  accept: 'teal',
  delivery: 'blue',
  appeal: 'orange',
  honor: 'indigo',
  reauthorize: 'red',
};

const LEGEND = [
  ['accept', 'Worker must accept'],
  ['delivery', 'Work is due'],
  ['honor', 'PayPal is holding the funds'],
  ['reauthorize', 'Authorization needs renewal'],
  ['appeal', 'Appeal is open'],
];

function asDate(iso) {
  if (!iso) return null;
  const value = /[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`;
  return new Date(value);
}

function contractIdOf(eventRecord) {
  const direct = eventRecord.contractId || eventRecord.get?.('contractId');
  if (direct) return direct;
  const id = String(eventRecord.id ?? '');
  const cut = id.lastIndexOf(':');
  return cut > 0 ? id.slice(0, cut) : '';
}

function viewFor(events) {
  const starts = events.map((event) => asDate(event.start).getTime());
  const ends = events.map((event) => asDate(event.end).getTime());
  const earliest = Math.min(...starts);
  const latest = Math.max(...ends);
  const span = Math.max(latest - earliest, 60 * 60 * 1000);
  const pad = Math.max(span * 0.08, 60 * 60 * 1000);
  let viewPreset = 'hourAndDay';
  if (span > 14 * 24 * 60 * 60 * 1000) viewPreset = 'weekAndDay';
  else if (span > 2 * 24 * 60 * 60 * 1000) viewPreset = 'dayAndWeek';
  return {
    startDate: new Date(earliest - pad),
    endDate: new Date(latest + pad),
    viewPreset,
  };
}

export function Schedule() {
  const schedule = useSchedule();
  const navigate = useNavigate();
  const data = schedule.data;
  const view = useMemo(() => (data?.events?.length ? viewFor(data.events) : null), [data]);

  if (schedule.isLoading) return <Spinner />;
  if (schedule.isError) return <Alert tone="danger">{problemOf(schedule.error).detail}</Alert>;

  const resources = data?.resources ?? [];
  const events = data?.events ?? [];

  return (
    <div className="flex flex-col gap-3">
      <p className="max-w-2xl text-sm text-ink-muted">
        When a worker must accept, when the work is due, how long PayPal will keep the hold, and
        when an appeal closes. The dates come from the contract and the authorization, so the
        calendar is read-only.
      </p>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
        {LEGEND.map(([kind, label]) => (
          <li key={kind}>{label}</li>
        ))}
      </ul>
      {resources.length === 0 || !view ? (
        <Card className="p-6 text-ink-muted">
          Nothing is on the clock yet. A window appears when a contract has a deadline, a PayPal
          hold, or an open appeal.
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <BryntumScheduler
            key={schedule.data.generated_at}
            height={640}
            resources={resources.map((row) => ({ id: row.id, name: row.name }))}
            events={events.map((event) => ({
              id: event.id,
              resourceId: event.resource_id,
              name: event.name,
              startDate: asDate(event.start),
              endDate: asDate(event.end),
              eventColor: EVENT_COLOR[event.kind] ?? 'blue',
              contractId: event.contract_id,
            }))}
            columns={[{ text: 'Contract', field: 'name', width: 280 }]}
            startDate={view.startDate}
            endDate={view.endDate}
            viewPreset={view.viewPreset}
            readOnly
            eventDragFeature={false}
            eventResizeFeature={false}
            eventEditFeature={false}
            eventDragCreateFeature={false}
            barMargin={8}
            rowHeight={48}
            listeners={{
              eventClick: ({ eventRecord }) => {
                const contractId = contractIdOf(eventRecord);
                if (contractId) navigate(`/contracts/${contractId}`);
              },
            }}
          />
        </Card>
      )}
      <p className="text-xs text-ink-muted">Settlement calendar · Bryntum Scheduler</p>
    </div>
  );
}
