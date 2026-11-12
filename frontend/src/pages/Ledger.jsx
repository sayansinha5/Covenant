import { LedgerGrid } from '../components/grid/LedgerGrid';
import { Card } from '../components/ui/Card';
import { Spinner } from '../components/ui/Spinner';
import { api } from '../lib/api';
import { useLedger } from '../lib/queries';

export function Ledger() {
  const ledger = useLedger();

  async function download() {
    const response = await api.get('/ledger/export.csv', { responseType: 'blob' });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'covenant-ledger.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <p className="max-w-xl text-sm text-ink-muted">
          Every hold, capture, fee and payout on this organization. Filter a direction or copy a
          PayPal reference without exporting the book first.
        </p>
        <button type="button" className="text-brand underline" onClick={() => void download()}>
          Download CSV
        </button>
      </div>
      <Card className="p-3">
        {ledger.isLoading ? <Spinner /> : <LedgerGrid rows={ledger.data?.items ?? []} />}
      </Card>
      <p className="text-xs text-ink-muted">Ledger grid · AG Grid</p>
    </div>
  );
}
