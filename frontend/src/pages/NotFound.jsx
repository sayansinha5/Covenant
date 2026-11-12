import { Link } from 'react-router-dom';

import { Card } from '../components/ui/Card';

export function NotFound() {
  return (
    <Card className="flex flex-col items-start gap-3 p-6">
      <h2 className="text-lg font-semibold">Page not found</h2>
      <p className="text-ink-muted">This page doesn't exist, or you don't have access to it.</p>
      <Link to="/overview" className="font-medium text-brand hover:underline">
        Go to Overview
      </Link>
    </Card>
  );
}
