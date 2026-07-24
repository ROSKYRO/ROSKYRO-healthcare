import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, CardHeader, Table, Badge, Button, PageLoading, formatCurrency, formatDate, formatDateTime } from '../../components/ui';

export default function CustomerSettlements() {
  const [settlements, setSettlements] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    api.get('/settlements')
      .then((res) => setSettlements(res.data.settlements))
      .catch((err) => { if (err?.response?.status === 402) setBlocked(true); });
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

  if (blocked) return <UpgradePrompt pillar="connect" />;
  if (!settlements) return <PageLoading />;

  const pendingTotal = settlements.filter((s) => s.status === 'pending').reduce((sum, s) => sum + Number(s.amount), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Referral Commission</h1>
        <p className="text-sm text-gray-500 mt-1">
          Jab aap kisi ROSKYRO CONNECT partner ko refer karte hain aur us par commission bantа hai, to wo commission
          seedha aapki business se partner ko jaata hai — ROSKYRO koi payment handle nahi karta, sirf connect karta hai.
          Partner ki UPI ID par direct pay karke yahan "I've Paid" click karein — lekin status "Paid" tabhi banega jab
          partner khud confirm karega ki unhe paisa mil gaya hai. Tab tak status "Pending" hi rahega.
        </p>
      </div>

      <Card className="p-5">
        <p className="text-sm text-gray-500">Pending commission you owe partners</p>
        <p className="text-2xl font-bold text-gray-900">{formatCurrency(pendingTotal)}</p>
      </Card>

      <Card>
        <CardHeader title="Settlements" subtitle="Har referral ke baad, agar koi settlement rule set hai, to yahan record ban jaata hai." />
        <Table
          rows={settlements}
          emptyMessage="Koi settlement abhi tak nahi bana."
          columns={[
            { key: 'referral_code', header: 'Referral' },
            { key: 'partner_org_name', header: 'Partner' },
            { key: 'partner_payout_upi_id', header: 'Pay partner at (UPI)', render: (r) => r.partner_payout_upi_id
              ? <span className="font-mono text-xs text-gray-700">{r.partner_payout_upi_id}</span>
              : <span className="text-xs text-rose-500">Partner ne abhi UPI set nahi ki</span> },
            { key: 'settlement_type', header: 'Type', render: (r) => <Badge tone="slate">{r.settlement_type.replace(/_/g, ' ')}</Badge> },
            { key: 'amount', header: 'Amount', render: (r) => formatCurrency(r.amount) },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'created_at', header: 'Date', render: (r) => formatDate(r.created_at) },
            { key: 'actions', header: '', render: (r) => {
              if (r.status === 'paid') return null;
              if (r.payer_marked_paid_at) {
                return (
                  <span className="text-xs text-amber-700" title={`You marked this paid on ${formatDateTime(r.payer_marked_paid_at)}`}>
                    Waiting for partner to confirm receipt
                  </span>
                );
              }
              return <Button size="sm" disabled={busyId === r.id} onClick={() => markPaid(r.id)}>I've Paid — Mark Paid</Button>;
            } },
          ]}
        />
      </Card>
    </div>
  );
}
