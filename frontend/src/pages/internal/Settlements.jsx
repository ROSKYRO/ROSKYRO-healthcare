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

  if (!settlements) return <PageLoading />;
  const pendingTotal = settlements.filter((s) => s.status === 'pending').reduce((sum, s) => sum + Number(s.amount), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settlements (Oversight Only)</h1>
        <p className="text-sm text-gray-500 mt-1">
          Generated automatically when a referral completes, based on each partner's configured settlement rule.
          Never assumed by default. ROSKYRO does not process this money — the referring business pays the partner
          directly at their Payout UPI ID. Normal path is two-sided: the business marks it paid, then the partner
          independently confirms receipt before status becomes "paid" — a business's own claim is never enough on
          its own. "Mark Paid" here is a dispute-resolution override that finalizes immediately, bypassing partner
          confirmation — use it only to resolve a dispute or record a payment a business reported through support.
        </p>
      </div>

      <Card className="p-5">
        <p className="text-sm text-gray-500">Pending commission total (unpaid, across all businesses)</p>
        <p className="text-2xl font-bold text-gray-900">{formatCurrency(pendingTotal)}</p>
      </Card>

      <Card>
        <Table
          rows={settlements}
          emptyMessage="No settlements generated yet."
          columns={[
            { key: 'referral_code', header: 'Referral' },
            { key: 'org_name', header: 'Business' },
            { key: 'partner_org_name', header: 'Partner' },
            { key: 'partner_payout_upi_id', header: 'Payout UPI', render: (r) => r.partner_payout_upi_id
              ? <span className="font-mono text-xs text-gray-700">{r.partner_payout_upi_id}</span>
              : <span className="text-xs text-rose-500">Not set yet</span> },
            { key: 'settlement_type', header: 'Type', render: (r) => <Badge tone="slate">{r.settlement_type.replace(/_/g, ' ')}</Badge> },
            { key: 'amount', header: 'Amount', render: (r) => formatCurrency(r.amount) },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'payer_marked_paid_at', header: 'Business claims paid', render: (r) => r.payer_marked_paid_at
              ? <span className="text-xs text-gray-600">{formatDateTime(r.payer_marked_paid_at)}</span>
              : <span className="text-xs text-gray-400">Not yet</span> },
            { key: 'created_at', header: 'Date', render: (r) => formatDate(r.created_at) },
            { key: 'actions', header: '', render: (r) => r.status === 'pending' && (
              <Button size="sm" disabled={busyId === r.id} onClick={() => markPaid(r.id)}>Mark Paid (override)</Button>
            ) },
          ]}
        />
      </Card>
    </div>
  );
}
