import { useEffect, useState, useCallback } from 'react';
import clsx from 'clsx';
import api from '../../lib/api';
import { Card, CardHeader, Table, Badge, Button, Input, PageLoading, formatCurrency, formatDate, formatDateTime } from '../../components/ui';

function PayoutSettings({ partner, onSaved }) {
  const [upiId, setUpiId] = useState(partner.payout_upi_id || '');
  const [note, setNote] = useState(partner.payout_note || '');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setSaved(false);
    try {
      await api.patch(`/partners/${partner.id}`, { payoutUpiId: upiId.trim(), payoutNote: note.trim() || null });
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
        title="Payout Settings"
        subtitle="Referral commission ROSKYRO se nahi, seedha us business se aayega jisne aapko refer kiya — wo isi UPI ID par direct pay karega. ROSKYRO sirf connect karta hai, payment handle nahi karta."
      />
      <form onSubmit={save} className="px-5 pb-5 space-y-4">
        <Input
          label="Payout UPI ID"
          value={upiId}
          onChange={(e) => setUpiId(e.target.value)}
          placeholder="yourclinic@okhdfcbank"
          required
        />
        <Input
          label="Payout note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. account holder name, alternate contact"
        />
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save Payout UPI'}</Button>
          {saved && <span className="text-sm text-emerald-600 font-medium">Saved ✓</span>}
        </div>
        {!partner.payout_upi_id && (
          <p className="text-xs text-rose-500">
            Abhi tak koi payout UPI ID set nahi hai — jab tak set nahi karoge, referring businesses ko pata nahi
            chalega ki commission kahan direct bhejna hai.
          </p>
        )}
      </form>
    </Card>
  );
}

function CommissionRateSettings({ partner, onSaved }) {
  const [rate, setRate] = useState(partner.commission_rate_percentage ?? '');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setSaved(false);
    setError(null);
    try {
      await api.put('/settlements/my-rate', { percentageRate: Number(rate) });
      setSaved(true);
      onSaved();
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not save commission rate.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Your Commission Rate"
        subtitle="Aap har completed referral par kitna % commission doge, wo yahan set karo — ye rate Partner Directory me har business ko publicly dikhega, aur usi ke base par businesses decide karenge ki aapko apna partner banayein ya nahi."
      />
      <form onSubmit={save} className="px-5 pb-5 space-y-4">
        <Input
          label="Commission per referral (%)"
          type="number" min="0" max="100" step="0.5"
          value={rate}
          onChange={(e) => setRate(e.target.value)}
          placeholder="e.g. 10"
          required
        />
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save Commission Rate'}</Button>
          {saved && <span className="text-sm text-emerald-600 font-medium">Saved ✓</span>}
        </div>
        {partner.commission_rate_percentage == null && (
          <p className="text-xs text-rose-500">
            Abhi tak koi commission rate set nahi hai — jab tak set nahi karoge, Partner Directory me businesses ko
            "commission rate not set" dikhega, jo unhein aapko partner banane se rok sakta hai.
          </p>
        )}
      </form>
    </Card>
  );
}

export default function PartnerSettlements() {
  const [settlements, setSettlements] = useState(null);
  const [partner, setPartner] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    Promise.all([api.get('/settlements'), api.get('/partners/me')]).then(([s, p]) => {
      setSettlements(s.data.settlements);
      setPartner(p.data.partner);
    });
  }, []);

  useEffect(load, [load]);

  async function confirmReceived(id) {
    setBusyId(id);
    try {
      await api.post(`/settlements/${id}/confirm-received`);
      load();
    } finally {
      setBusyId(null);
    }
  }

  if (!settlements || !partner) return <PageLoading />;

  const total = settlements.reduce((sum, s) => sum + Number(s.amount), 0);
  const pending = settlements.filter((s) => s.status === 'pending').reduce((sum, s) => sum + Number(s.amount), 0);
  const awaitingConfirmation = settlements.filter((s) => s.status === 'pending' && s.payer_marked_paid_at).length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settlements</h1>
        <p className="text-sm text-gray-500 mt-1">
          Settlement is configured per partnership and is never assumed — some referrals carry no settlement at all.
          Commission comes directly from the referring business to your Payout UPI ID below — ROSKYRO never holds or moves this money.
          Jab business "I've Paid" click karta hai, status turant "Paid" nahi banta — aapko khud "Confirm Received" click
          karna hoga jab paisa actually mil jaaye. Tab tak status "Pending" hi dikhega.
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-5">
        <Card className="p-5">
          <p className="text-sm text-gray-500">Total settlement value</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(total)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-gray-500">Pending payout (not yet received)</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(pending)}</p>
        </Card>
        <Card className={clsx('p-5', awaitingConfirmation > 0 && 'ring-2 ring-amber-300')}>
          <p className="text-sm text-gray-500">Awaiting your confirmation</p>
          <p className="text-2xl font-bold text-gray-900">{awaitingConfirmation}</p>
        </Card>
      </div>

      <CommissionRateSettings partner={partner} onSaved={load} />

      <PayoutSettings partner={partner} onSaved={load} />

      <Card>
        <Table
          rows={settlements}
          emptyMessage="No settlements yet."
          columns={[
            { key: 'referral_code', header: 'Referral' },
            { key: 'org_name', header: 'From Business' },
            { key: 'settlement_type', header: 'Type', render: (r) => <Badge tone="slate">{r.settlement_type.replace(/_/g, ' ')}</Badge> },
            { key: 'amount', header: 'Amount', render: (r) => formatCurrency(r.amount) },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'period_month', header: 'Period' },
            { key: 'created_at', header: 'Date', render: (r) => formatDate(r.created_at) },
            { key: 'actions', header: '', render: (r) => {
              if (r.status === 'paid') return null;
              if (!r.payer_marked_paid_at) return <span className="text-xs text-gray-400">Not yet marked paid by business</span>;
              return (
                <div className="flex flex-col items-start gap-1">
                  <span className="text-xs text-amber-700" title={`Business marked this paid on ${formatDateTime(r.payer_marked_paid_at)}`}>
                    Business says paid
                  </span>
                  <Button size="sm" disabled={busyId === r.id} onClick={() => confirmReceived(r.id)}>
                    {busyId === r.id ? 'Confirming…' : 'Confirm Received'}
                  </Button>
                </div>
              );
            } },
          ]}
        />
      </Card>
    </div>
  );
}
