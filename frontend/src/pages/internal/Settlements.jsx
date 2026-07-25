import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { Card, Table, Badge, Button, PageLoading, formatCurrency, formatDate, formatDateTime } from '../../components/ui';

export default function InternalSettlements() {
  const [settlements, setSettlements] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    api.get('/settlements').then((res) => setSettlements(res.data.settlements));
  }, []);

  useEffect(load, [load]);

  async function markPaid(id) {
    setBusyId(id);
    try {
      await api.post(`/settlements/${id}/mark-paid`);
      load();
    } finally {
      setBusyId(null);
    }
  }

  async function confirmReceived(id) {
    setBusyId(id);
    try {
      await api.post(`/settlements/${id}/confirm-received`);
      load();
    } finally {
      setBusyId(null);
    }
  }

  if (!settlements) return <PageLoading />;
  const pendingTotal = settlements.filter((s) => s.status === 'pending').reduce((sum, s) => sum + Number(s.amount), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Marketing Fees (Collection Oversight)</h1>
        <p className="text-sm text-gray-500 mt-1">
          Generated automatically when a referral completes, based on the partner's configured Marketing Fee rule
          (always a flat rupee amount — percentage-based commission has been removed entirely). A patient referral is
          treated as marketing the referring business did for the partner, so this fee is owed by the PARTNER,
          straight to ROSKYRO — not to the referring business. Normal path is two-sided: the partner marks it paid,
          then ROSKYRO internal independently confirms receipt before status becomes "paid". "Mark Paid" here is a
          dispute-resolution override that finalizes immediately (use it only when a partner reported the payment
          through support). Once collected, ROSKYRO periodically pays a fixed % of these fees back to the referring
          business as a Marketing Fee Payout — see the "Marketing Fee Payouts" page for that side of the flow.
        </p>
      </div>

      <Card className="p-5">
        <p className="text-sm text-gray-500">Pending Marketing Fees total (unpaid, across all partners)</p>
        <p className="text-2xl font-bold text-gray-900">{formatCurrency(pendingTotal)}</p>
      </Card>

      <Card>
        <Table
          rows={settlements}
          emptyMessage="No Marketing Fees generated yet."
          columns={[
            { key: 'referral_code', header: 'Referral' },
            { key: 'org_name', header: 'Referring Business' },
            { key: 'partner_org_name', header: 'Partner (payer)' },
            { key: 'amount', header: 'Marketing Fee', render: (r) => formatCurrency(r.amount) },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'payer_marked_paid_at', header: 'Partner claims paid', render: (r) => r.payer_marked_paid_at
              ? (
                <div>
                  <span className="text-xs text-gray-600">{formatDateTime(r.payer_marked_paid_at)}</span>
                  {r.payment_reference && <p className="text-xs text-gray-400 font-mono">Ref: {r.payment_reference}</p>}
                </div>
              )
              : <span className="text-xs text-gray-400">Not yet</span> },
            { key: 'created_at', header: 'Date', render: (r) => formatDate(r.created_at) },
            { key: 'actions', header: '', render: (r) => {
              if (r.status === 'paid') return null;
              if (r.payer_marked_paid_at) {
                return (
                  <Button size="sm" disabled={busyId === r.id} onClick={() => confirmReceived(r.id)}>
                    {busyId === r.id ? 'Confirming…' : 'Confirm Received'}
                  </Button>
                );
              }
              return (
                <Button size="sm" variant="secondary" disabled={busyId === r.id} onClick={() => markPaid(r.id)}>
                  {busyId === r.id ? '…' : 'Mark Paid (override)'}
                </Button>
              );
            } },
          ]}
        />
      </Card>
    </div>
  );
}
