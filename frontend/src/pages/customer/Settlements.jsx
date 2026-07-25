import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, CardHeader, Table, Badge, Input, Button, PageLoading, formatCurrency } from '../../components/ui';

function PayoutAccountSettings({ org, onSaved }) {
  const [upiId, setUpiId] = useState(org.marketing_payout_upi_id || '');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setSaved(false);
    try {
      await api.patch(`/orgs/${org.id}`, { marketingPayoutUpiId: upiId.trim() });
      setSaved(true);
      onSaved();
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Payout Account"
        subtitle="Jahan ROSKYRO aapka Marketing Fee Payout (har period ka fixed % share) bhejega."
      />
      <form onSubmit={save} className="px-5 pb-5 space-y-4">
        <Input
          label="Payout UPI ID"
          value={upiId}
          onChange={(e) => setUpiId(e.target.value)}
          placeholder="yourbusiness@okhdfcbank"
          required
        />
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save Payout UPI'}</Button>
          {saved && <span className="text-sm text-emerald-600 font-medium">Saved ✓</span>}
        </div>
        {!org.marketing_payout_upi_id && (
          <p className="text-xs text-rose-500">
            Abhi tak koi payout UPI ID set nahi hai — jab tak set nahi karoge, ROSKYRO aapko Marketing Fee Payout
            nahi bhej payega.
          </p>
        )}
      </form>
    </Card>
  );
}

export default function CustomerSettlements() {
  const { user } = useAuth();
  const [payouts, setPayouts] = useState(null);
  const [rate, setRate] = useState(null);
  const [org, setOrg] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [downloadingId, setDownloadingId] = useState(null);

  const load = useCallback(() => {
    // Note: only your own incoming Marketing Fee Payout is shown here.
    // Per-referral partner fee amounts (what a partner pays ROSKYRO) are
    // internal/partner-facing only and aren't fetched or shown on this page.
    Promise.all([
      api.get('/settlements/marketing-payouts'),
      api.get('/settlements/marketing-fee-rate'),
      api.get(`/orgs/${user.orgId}`),
    ])
      .then(([p, r, o]) => {
        setPayouts(p.data.payouts);
        setRate(r.data.percentage);
        setOrg(o.data.organization);
      })
      .catch((err) => { if (err?.response?.status === 402) setBlocked(true); });
  }, [user.orgId]);

  useEffect(load, [load]);

  async function downloadInvoice(payout) {
    setDownloadingId(payout.id);
    try {
      const res = await api.get(`/settlements/marketing-payouts/${payout.id}/invoice`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${payout.invoice_number}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } finally {
      setDownloadingId(null);
    }
  }

  if (blocked) return <UpgradePrompt pillar="connect" />;
  if (!payouts || rate == null || !org) return <PageLoading />;

  const totalReceived = payouts.filter((p) => p.status === 'paid').reduce((sum, p) => sum + Number(p.payout_amount), 0);
  const pendingPayout = payouts.filter((p) => p.status === 'pending').reduce((sum, p) => sum + Number(p.payout_amount), 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Marketing Fee Payouts</h1>
        <p className="text-sm text-gray-500 mt-1">
          Jab aap kisi ROSKYRO Networking Marketing partner ko patient refer karte hain, to ise us partner ke liye aapki taraf se
          ki gayi marketing maana jaata hai. ROSKYRO har period (month) collect hui Marketing Fees ka ek fixed{' '}
          <span className="font-semibold">{rate}%</span> aapko wapas deta hai, ek Marketing Fee Payout ke roop mein,
          seedha aapki payout UPI ID par — har payout ke saath ek invoice bhi milta hai.
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <Card className="p-5">
          <p className="text-sm text-gray-500">Received from ROSKYRO so far</p>
          <p className="text-2xl font-bold text-emerald-700">{formatCurrency(totalReceived)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-gray-500">Pending payout (generated, not yet paid)</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(pendingPayout)}</p>
        </Card>
      </div>

      <PayoutAccountSettings org={org} onSaved={load} />

      <Card>
        <CardHeader title="Marketing Fee Payouts" subtitle="ROSKYRO se mile (ya milne wale) periodic payouts, invoice ke saath." />
        <Table
          rows={payouts}
          emptyMessage="Abhi tak koi payout generate nahi hua. ROSKYRO team period-end par isko generate karti hai."
          columns={[
            { key: 'period', header: 'Period' },
            { key: 'referral_count', header: 'Referrals' },
            { key: 'total_fees_collected', header: 'Fees Collected', render: (r) => formatCurrency(r.total_fees_collected) },
            { key: 'payout_percentage', header: 'Rate', render: (r) => `${r.payout_percentage}%` },
            { key: 'payout_amount', header: 'Payout Amount', render: (r) => formatCurrency(r.payout_amount) },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'invoice_number', header: 'Invoice', render: (r) => (
              <Button size="sm" variant="secondary" disabled={downloadingId === r.id} onClick={() => downloadInvoice(r)}>
                {downloadingId === r.id ? 'Downloading…' : `⬇ ${r.invoice_number}`}
              </Button>
            ) },
          ]}
        />
      </Card>
    </div>
  );
}
