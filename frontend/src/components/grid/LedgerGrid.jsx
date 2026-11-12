import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { AllCommunityModule, themeQuartz } from 'ag-grid-community';
import { AgGridProvider, AgGridReact } from 'ag-grid-react';

import { TextInput } from '../ui/Field';
import { Spinner } from '../ui/Spinner';
import { formatDateTime, formatMoney } from '../../lib/format';

const LICENSE_KEY = import.meta.env.VITE_AG_GRID_LICENSE_KEY || '';
const theme = themeQuartz.withParams({
  fontFamily: 'Inter Variable, ui-sans-serif, system-ui, sans-serif',
  fontSize: 13,
});

function compareMoney(left, right) {
  const [wholeA, fractionA = '00'] = String(left ?? '').split('.');
  const [wholeB, fractionB = '00'] = String(right ?? '').split('.');
  const a = `${wholeA.padStart(12, '0')}.${fractionA.padEnd(2, '0')}`;
  const b = `${wholeB.padStart(12, '0')}.${fractionB.padEnd(2, '0')}`;
  if (a < b) return -1;
  if (a > b) return 1;
  return 0;
}

function ContractCell(params) {
  const row = params.data;
  if (!row?.contract_id) return null;
  return (
    <Link to={`/contracts/${row.contract_id}`} className="text-brand">
      {row.contract_number || 'Contract'}
    </Link>
  );
}

function useGridModules() {
  const [modules, setModules] = useState(LICENSE_KEY ? null : [AllCommunityModule]);
  const [enterprise, setEnterprise] = useState(false);

  useEffect(() => {
    if (!LICENSE_KEY) return undefined;
    let live = true;
    import('ag-grid-enterprise')
      .then((pkg) => {
        if (!live) return;
        setModules([pkg.AllEnterpriseModule]);
        setEnterprise(true);
      })
      .catch(() => {
        if (live) setModules([AllCommunityModule]);
      });
    return () => {
      live = false;
    };
  }, []);

  return { modules, enterprise };
}

export function LedgerGrid({ rows }) {
  const { modules, enterprise } = useGridModules();
  const [quickFilter, setQuickFilter] = useState('');
  const columnDefs = useMemo(() => {
    const directionFilter = enterprise ? 'agSetColumnFilter' : true;
    return [
      {
        field: 'created_at',
        headerName: 'When',
        minWidth: 180,
        valueFormatter: (params) => formatDateTime(params.value),
      },
      {
        headerName: 'Contract',
        minWidth: 120,
        cellRenderer: ContractCell,
        valueGetter: (params) => params.data?.contract_number ?? '',
      },
      {
        field: 'direction',
        headerName: 'Direction',
        minWidth: 130,
        filter: directionFilter,
        enableRowGroup: enterprise,
      },
      { field: 'entry_type', headerName: 'Account', minWidth: 120 },
      {
        field: 'amount',
        headerName: 'Amount',
        minWidth: 120,
        comparator: compareMoney,
        valueFormatter: (params) =>
          params.value ? formatMoney(params.value, params.data?.currency) : '',
      },
      { field: 'paypal_reference', headerName: 'PayPal reference', minWidth: 180 },
      { field: 'actor_type', headerName: 'Actor', minWidth: 120 },
    ];
  }, [enterprise]);

  if (!modules) return <Spinner />;

  return (
    <AgGridProvider modules={modules} licenseKey={LICENSE_KEY || undefined}>
      <div className="flex flex-col gap-3">
        <TextInput
          value={quickFilter}
          onChange={(event) => setQuickFilter(event.target.value)}
          placeholder="Filter by contract, direction, or PayPal reference"
          aria-label="Filter the ledger"
        />
        <div className="h-[560px] w-full">
          <AgGridReact
            theme={theme}
            rowData={rows}
            columnDefs={columnDefs}
            quickFilterText={quickFilter}
            getRowId={(params) => params.data.id}
            defaultColDef={{ sortable: true, filter: true, resizable: true, flex: 1 }}
            pagination
            paginationPageSize={25}
            paginationPageSizeSelector={[25, 50, 100]}
            enableCellTextSelection
            rowGroupPanelShow={enterprise ? 'always' : undefined}
            statusBar={
              enterprise
                ? {
                    statusPanels: [
                      { statusPanel: 'agTotalAndFilteredRowCountComponent', align: 'left' },
                    ],
                  }
                : undefined
            }
            overlayNoRowsTemplate="No ledger entries yet."
          />
        </div>
      </div>
    </AgGridProvider>
  );
}
