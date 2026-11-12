import { lazy, Suspense } from 'react';

import { Spinner } from '../components/ui/Spinner';

const Schedule = lazy(() => import('./Schedule').then((module) => ({ default: module.Schedule })));

export function ScheduleRoute() {
  return (
    <Suspense fallback={<Spinner />}>
      <Schedule />
    </Suspense>
  );
}
