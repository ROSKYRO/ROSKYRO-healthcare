import { useEffect, useState, useCallback } from 'react';
import clsx from 'clsx';
import api from '../../lib/api';
import { Card, CardHeader, Table, Badge, Button, Input, PageLoading, formatCurrency, formatDate, formatDateTime } from '../../components/ui';

function MarketingFeeRateSettings({ partner, myRate, onSaved }) {
  // `myRate` (from GET /settlements/my-rate) is the partner's OWN explicit
  // rate -- null if they've never set one. `partner.referral_bonus_amount`
  // (from GET /partners/me) is the EFFECTIVE amount currently shown to
  // businesses in the Partner Directory, which falls back to ROSKYRO's
  // category/platform default when the partner hasn't set their own --
  // these two are deliberately kept separate so the input below only ever
  // reflects what THIS partner actually chose, never a default they never
  // agreed to (saving an unedited pre-filled default would silently lock
  // it in as if they'd chosen it themselves).
  const ownAmount = myRate?.flat_fee_amount;
  const [amount, setAmount] = useState(ownAmount ?? '');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setSaved(false);
    setError(null);
    try {
      await api.put('/settlements/my-rate', { flatFeeAmount: Number(amount) });
      setSaved(true);
      onSaved();
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not save Marketing Fee amount.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader
        title="Your Marketing Fee"
        subtitle="Har patient referral ek business dwara aapke liye ki gayi marketing maana jaata hai — isliye aap har completed referral par ROSKYRO ko kitna flat Marketing Fee (₹ rupees me) doge, wo yahan set karo. Ye amount Partner Directory me har business ko publicly dikhega. Koi percentage/commission nahi — sirf ek fixed rupee amount, aur ye seedha ROSKYRO ko jaata hai, referring business ko nahi."
      />
      <form onSubmit={save} className="px-5 pb-5 space-y-4">
        {ownAmount == null && partner.referral_bonus_amount != null && (
          <p className="text-xs text-gray-500">
            Aapne abhi tak apna khud ka rate set nahi kiya — filhaal businesses ko ROSKYRO ka default fee{' '}
            <span className="font-semibold text-gray-700">{formatCurrency(partner.referral_bonus_amount)}</span> (aapki
            category ke hisab se) dikh raha hai. Neeche apna khud ka amount set karke isse override kar sakte ho.
          </p>
        )}
        <Input
          label="Marketing Fee per referral (₹)"
          type="number" min="0" step="10"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          placeholder="e.g. 300"
          required
        />
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save Marketing Fee'}</Button>
          {saved && <span className="text-sm text-emerald-600 font-medium">Saved ✓</span>}
        </div>
        {ownAmount == null && partner.referral_bonus_amount == null && (
          <p className="text-xs text-rose-500">
            Abhi tak koi Marketing Fee amount set nahi hai — jab tak set nahi karoge, Partner Directory me businesses ko
            "Marketing Fee not set" dikhega, jo unhein aapko partner banane se rok sakta hai.
          </p>
        )}
      </form>
    </Card>
  );
}

function WhereToPay({ roskyroUpiId }) {
  return (
    <Card>
      <CardHeader
        title="Where to pay ROSKYRO"
        subtitle="Patient referral ab marketing ki tarah treat hoti hai — jo bhi Marketing Fee aap referral ke liye dete hain, wo seedha ROSKYRO ko jaata hai (referring business ko direct nahi), aur ROSKYRO usi collection me se har mahine ek fixed % un businesses ko wapas deta hai jinhone aapko refer kiya."
      />
      <div className="px-5 pb-5">
        {roskyroUpiId ? (
          <p className="text-sm text-gray-700">
            Pay to: <span className="font-mono font-semibold text-brand-700">{roskyroUpiId}</span>
          </p>
        ) : (
          <p className="text-xs text-gray-400">ROSKYRO ne abhi collection UPI ID set nahi ki hai.</p>
        )}
      </div>
    </Card>
  );
}

export default function Wallet() {
  const [settlements, setSettlements] = useState(null);
  const [partner, setPartner] = useState(null);
  const [myRate, setMyRate] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [refDrafts, setRefDrafts] = useState({});
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setError('');
    Promise.all([api.get('/settlements'), api.get('/partners/me'), api.get('/settlements/my-rate')]).then(([s, p, mr]) => {
      setSettlements(s.data.settlements);
      setPartner(p.data.partner);
      setMyRate(mr.data.rate);
    }).catch(() => {
      setError('Could not load your wallet. Please try again.');
    });
  }, []);

  useEffect(load, [load]);

  async function markPaid(id) {
    setBusyId(id);
    setError('');
    try {
      const paymentReference = (refDrafts[id] || '').trim() || undefined;
      await api.post(`/settlements/${id}/mark-paid`, { paymentReference });
      setRefDrafts((prev) => ({ ...prev, [id]: '' }));
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not mark this as paid. Please try again.');
    } finally {
      setBusyId(null);
    }
  }

  if (error && (!settlements || !partner)) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!settlements || !partner) return <PageLoading />;

  const totalOwed = settlements.reduce((sum, s) => sum + Number(s.amount), 0);
  const totalPaid = settlements.filter((s) => s.status === 'paid').reduce((sum, s) => sum + Number(s.amount), 0);
  const pending = settlements.filter((s) => s.status === 'pending').reduce((sum, s) => sum + Number(s.amount), 0);
  const awaitingRoskyroConfirmation = settlements.filter((s) => s.status === 'pending' && s.payer_marked_paid_at).length;
  const roskyroUpiId = settlements.find((s) => s.roskyro_payout_upi_id)?.roskyro_payout_upi_id || null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Wallet</h1>
        <p className="text-sm text-gray-500 mt-1">
          Har referral yahan ek Marketing Fee ke roop mein dikhta hai jo aap ROSKYRO ko owe karte hain (patient referral
          ko referring business ki taraf se ki gayi marketing maana jaata hai). Ye paisa ROSKYRO ko jaata hai — koi
          bhi referring business ko direct nahi. Jab aap "I've Paid ROSKYRO" click karte hain, status turant "Paid"
          nahi banta — ROSKYRO team khud confirm karegi jab paisa actually mil jaaye. Tab tak status "Pending" hi
          dikhega.
        </p>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <div className="grid md:grid-cols-4 gap-5">
        <Card className="p-5">
          <p className="text-sm text-gray-500">Total Marketing Fees (all-time)</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(totalOwed)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-gray-500">Paid to ROSKYRO so far</p>
          <p className="text-2xl font-bold text-emerald-700">{formatCurrency(totalPaid)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-gray-500">Pending (not yet paid)</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(pending)}</p>
        </Card>
        <Card className={clsx('p-5', awaitingRoskyroConfirmation > 0 && 'ring-2 ring-amber-300')}>
          <p className="text-sm text-gray-500">Awaiting ROSKYRO confirmation</p>
          <p className="text-2xl font-bold text-gray-900">{awaitingRoskyroConfirmation}</p>
        </Card>
      </div>

      <MarketingFeeRateSettings partner={partner} myRate={myRate} onSaved={load} />

      <WhereToPay roskyroUpiId={roskyroUpiId} />

      <Card>
        <CardHeader title="Marketing Fee Ledger" subtitle="Complete history of Marketing Fees owed per referral, and payment status." />
        <Table
          rows={settlements}
          emptyMessage="No Marketing Fee records yet."
          columns={[
            { key: 'referral_code', header: 'Referral' },
            { key: 'org_name', header: 'Referred By' },
            { key: 'amount', header: 'Marketing Fee', render: (r) => formatCurrency(r.amount) },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'period_month', header: 'Period' },
            { key: 'created_at', header: 'Date', render: (r) => formatDate(r.created_at) },
            { key: 'actions', header: '', render: (r) => {
              if (r.status === 'paid') return null;
              if (r.payer_marked_paid_at) {
                return (
                  <span className="text-xs text-amber-700" title={`You marked this paid on ${formatDateTime(r.payer_marked_paid_at)}${r.payment_reference ? ` · Ref: ${r.payment_reference}` : ''}`}>
                    Waiting for ROSKYRO to confirm
                  </span>
                );
              }
              return (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    placeholder="Payment ref (optional)"
                    value={refDrafts[r.id] || ''}
                    onChange={(e) => setRefDrafts((prev) => ({ ...prev, [r.id]: e.target.value }))}
                    className="text-xs border border-gray-200 rounded px-2 py-1 w-32"
                  />
                  <Button size="sm" disabled={busyId === r.id} onClick={() => markPaid(r.id)}>
                    {busyId === r.id ? 'Marking…' : "I've Paid ROSKYRO"}
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
