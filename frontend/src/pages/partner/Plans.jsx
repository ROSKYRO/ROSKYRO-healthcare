import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import PricingCards from '../../components/PricingCards';
import AddonCard from '../../components/AddonCard';
import { Card, Badge, Button, PageLoading, formatCurrency, formatDate, formatDateTime } from '../../components/ui';
import { upiPaymentQrDataUrl } from '../../lib/upiQr';

// Pillar codes stay lowercase internally ('grow'/'manage'/'connect'), but
// 'connect' now displays as "Networking Marketing" everywhere in the UI.
const PILLAR_DISPLAY_NAMES = { grow: 'GROW', manage: 'MANAGE', connect: 'Networking Marketing' };

function CheckoutModal({ plan, cycle, payment, onConfirm, onCancel, busy }) {
  const [copied, setCopied] = useState(false);
  const [qrDataUrl, setQrDataUrl] = useState(null);
  const price = cycle === 'yearly' ? plan.yearly_price : plan.monthly_price;
  // Same fix as customer/Plans.jsx: if ROSKYRO hasn't set its own platform
  // UPI ID yet (Pricing & Payments, super admin), there's no real payment
  // destination -- show a clear message instead of an endless loading
  // skeleton, and don't allow "I've Paid" to be submitted.
  const upiConfigured = Boolean(payment?.upi_id);

  useEffect(() => {
    let cancelled = false;
    if (!upiConfigured) return;
    setQrDataUrl(null);
    upiPaymentQrDataUrl({ upiId: payment.upi_id, amount: price, note: `ROSKYRO ${plan.name}` })
      .then((url) => { if (!cancelled) setQrDataUrl(url); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [payment.upi_id, price, plan.name, upiConfigured]);

  function copyUpi() {
    navigator.clipboard?.writeText(payment.upi_id).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <Card className="max-w-md w-full p-6">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Activate {plan.name}</p>
        <p className="text-2xl font-extrabold text-gray-900 mt-1">
          {formatCurrency(price)}<span className="text-sm font-normal text-gray-400">/{cycle === 'yearly' ? 'year' : 'month'}</span>
        </p>
        <p className="text-xs text-brand-700 font-semibold uppercase tracking-wide">{cycle === 'yearly' ? 'Annual Membership' : 'Monthly Subscription'}</p>

        {upiConfigured ? (
          <div className="mt-5 bg-gray-50 border border-gray-200 rounded-xl p-4">
            <p className="text-xs text-gray-400 text-center">Scan &amp; pay via any UPI app</p>
            <div className="flex justify-center mt-2">
              {qrDataUrl ? (
                <img src={qrDataUrl} alt="UPI payment QR code" width={180} height={180} className="rounded-lg border border-gray-200 bg-white" />
              ) : (
                <div className="w-[180px] h-[180px] bg-gray-100 animate-pulse rounded-lg" />
              )}
            </div>
            <div className="flex items-center justify-between mt-4">
              <div>
                <p className="text-xs text-gray-400">or pay to this UPI ID</p>
                <p className="text-lg font-bold text-gray-900">{payment.upi_id}</p>
              </div>
              <Button size="sm" variant="secondary" onClick={copyUpi}>{copied ? 'Copied!' : 'Copy'}</Button>
            </div>
            <p className="text-sm text-gray-500 mt-3">{payment.payment_note}</p>
          </div>
        ) : (
          <div className="mt-5 bg-rose-50 border border-rose-200 rounded-xl p-4">
            <p className="text-sm font-semibold text-rose-800">Payment collection abhi set up nahi hai</p>
            <p className="text-xs text-rose-700 mt-1">
              ROSKYRO ne apna UPI ID abhi Pricing &amp; Payments mein add nahi kiya hai, isliye is plan ke liye
              payment nahi liya ja sakta. Kripya ROSKYRO support se contact karein — jab tak ye set nahi hota,
              "I've Paid" submit karna disable rahega.
            </p>
          </div>
        )}

        <p className="text-xs text-gray-500 mt-4 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
          Payment karne ke baad "I've Paid" dabayein — ROSKYRO team payment verify karke aapka plan confirm karegi,
          tabhi ye pillar active hoga.
        </p>

        <div className="mt-4 flex items-center gap-3">
          <Button variant="secondary" className="flex-1" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button className="flex-1" onClick={onConfirm} disabled={busy || !upiConfigured}>{busy ? 'Submitting…' : "I've Paid — Submit for Confirmation"}</Button>
        </div>
      </Card>
    </div>
  );
}

function PendingActivations({ subscriptions, onWithdraw, withdrawingCode }) {
  const pending = subscriptions.filter((s) => s.status === 'pending_payment');
  if (pending.length === 0) return null;

  return (
    <Card className="p-5 bg-amber-50 border-amber-200">
      <p className="text-sm font-semibold text-gray-900">Awaiting ROSKYRO confirmation</p>
      <p className="text-xs text-gray-500 mt-1">
        Aapne payment submit kar diya hai — ROSKYRO team UPI payment verify karke jaldi confirm karegi, tab ye pillar(s) active honge.
      </p>
      <div className="mt-3 space-y-2">
        {pending.map((s) => (
          <div key={s.id} className="flex items-center justify-between bg-white border border-amber-100 rounded-lg px-3 py-2">
            <div>
              <p className="text-sm font-medium text-gray-900">{s.name}</p>
              <p className="text-xs text-gray-400">
                {formatCurrency(s.price_at_purchase ?? s.monthly_price)}/{s.billing_cycle === 'yearly' ? 'yr' : 'mo'} · submitted {formatDateTime(s.requested_at)}
              </p>
            </div>
            <Button size="sm" variant="ghost" disabled={withdrawingCode === s.plan_code} onClick={() => onWithdraw(s.plan_code)}>
              {withdrawingCode === s.plan_code ? '…' : 'Withdraw'}
            </Button>
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function PartnerPlans() {
  const { refreshPillars } = useAuth();
  const [plans, setPlans] = useState(null);
  const [mine, setMine] = useState(null);
  const [payment, setPayment] = useState(null);
  const [busyCode, setBusyCode] = useState(null);
  const [addonBusy, setAddonBusy] = useState(false);
  const [error, setError] = useState('');
  const [checkout, setCheckout] = useState(null); // { plan, cycle }

  const load = useCallback(() => {
    setError('');
    Promise.all([api.get('/partner-plans'), api.get('/partner-plans/mine'), api.get('/settings/payment')]).then(([p, m, s]) => {
      setPlans(p.data.plans);
      setMine(m.data);
      setPayment(s.data);
    }).catch(() => {
      setError('Could not load your plans. Please try again.');
    });
  }, []);

  useEffect(load, [load]);

  function startCheckout(plan, cycle) {
    setError('');
    setCheckout({ plan, cycle });
  }

  async function confirmSubscribe() {
    if (!checkout) return;
    const { plan, cycle } = checkout;
    setError('');
    setBusyCode(plan.code);
    try {
      await api.post('/partner-plans/subscribe', { planCode: plan.code, billingCycle: cycle });
      await refreshPillars();
      setCheckout(null);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not activate this plan.');
      setCheckout(null);
    } finally {
      setBusyCode(null);
    }
  }

  async function cancel(planCode) {
    setError('');
    setBusyCode(planCode);
    try {
      await api.post('/partner-plans/cancel', { planCode });
      await refreshPillars();
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not cancel this plan.');
    } finally {
      setBusyCode(null);
    }
  }

  // NOTE (round 23): activating the add-on is also a self-serve subscription
  // claim -- the backend always creates a pending_payment row for it, exactly
  // like a pillar -- so it goes through the same UPI QR CheckoutModal below
  // via startCheckout(), instead of calling /partner-plans/subscribe directly.

  async function cancelAddon(addon) {
    setError('');
    setAddonBusy(true);
    try {
      await api.post('/partner-plans/cancel', { planCode: addon.code });
      await refreshPillars();
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not cancel this add-on.');
    } finally {
      setAddonBusy(false);
    }
  }

  if (error && (!plans || !mine || !payment)) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }
  if (!plans || !mine || !payment) return <PageLoading />;

  const reelsAddon = plans.find((p) => p.code === 'reels');
  const reelsSub = mine.subscriptions.find((s) => s.plan_code === 'reels' && s.status === 'active');
  const reelsPending = mine.subscriptions.some((s) => s.plan_code === 'reels' && s.status === 'pending_payment');

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Plans & Billing</h1>
        <p className="text-sm text-gray-500 mt-1">
          Activate ROSKYRO pillars on your partner account — same services as the business side, partner pricing.
        </p>
      </div>

      <Card className="p-5 flex items-center justify-between flex-wrap gap-4">
        <div>
          <p className="text-sm text-gray-500">Your current monthly total</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(mine.monthlyTotal)}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {mine.activePillars.length === 0 && <span className="text-sm text-gray-400">No pillar active yet — pick one below to get started.</span>}
          {mine.activePillars.map((p) => {
            const sub = mine.subscriptions.find((s) => s.plan_code === p && s.status === 'active');
            const isFreeBonus = sub && Number(sub.price_at_purchase) === 0;
            return (
              <Badge key={p} tone="verified">
                {PILLAR_DISPLAY_NAMES[p] || p.toUpperCase()} active{isFreeBonus ? ' · free bonus' : ''}
              </Badge>
            );
          })}
        </div>
      </Card>

      <Card className="p-4 bg-gray-50 border-gray-200 flex items-center gap-3">
        <span className="text-lg">{'\u{1F4B3}'}</span>
        <p className="text-sm text-gray-600">
          Subscriptions are activated via UPI payment — pick a plan below, scan the QR code (or pay to the UPI ID
          shown) and submit. A pillar goes live once ROSKYRO's team confirms the payment.
        </p>
      </Card>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <PendingActivations subscriptions={mine.subscriptions} onWithdraw={cancel} withdrawingCode={busyCode} />

      <PricingCards
        plans={plans}
        activeCodes={mine.activePillars.includes('grow') && mine.activePillars.includes('manage') && mine.activePillars.includes('connect')
          ? [...mine.activePillars, 'complete']
          : mine.activePillars}
        onSelect={startCheckout}
        ctaLabel="Activate"
        busyCode={busyCode}
      />

      {reelsAddon && (
        <AddonCard
          addon={reelsAddon}
          isActive={!!reelsSub}
          isPending={reelsPending}
          requiredPillarActive={mine.activePillars.includes(reelsAddon.requires_pillar)}
          busy={addonBusy || busyCode === reelsAddon.code}
          onSubscribe={() => startCheckout(reelsAddon, 'monthly')}
          onCancel={() => cancelAddon(reelsAddon)}
        />
      )}

      <Card>
        <div className="px-5 pt-5">
          <h3 className="text-base font-semibold text-gray-900">Subscription history</h3>
        </div>
        <div className="px-5 pb-5 divide-y divide-gray-100 mt-2">
          {mine.subscriptions.length === 0 ? (
            <p className="text-sm text-gray-400 py-4">No subscriptions yet.</p>
          ) : (
            mine.subscriptions.map((s) => (
              <div key={s.id} className="py-3 flex items-center justify-between text-sm">
                <div>
                  <p className="font-medium text-gray-900">{s.name}</p>
                  <p className="text-xs text-gray-400">
                    {formatCurrency(s.price_at_purchase ?? s.monthly_price)}/{s.billing_cycle === 'yearly' ? 'yr' : 'mo'}
                    {' '}({s.billing_cycle === 'yearly' ? 'Annual Membership' : 'Monthly Subscription'})
                    {' '}· {s.started_at ? `started ${formatDate(s.started_at)}` : `submitted ${formatDate(s.requested_at)}`}
                    {s.cancelled_at ? ` · cancelled ${formatDate(s.cancelled_at)}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge tone={s.status}>{s.status}</Badge>
                  {(s.status === 'active' || s.status === 'pending_payment') && (
                    <Button size="sm" variant="ghost" disabled={busyCode === s.plan_code} onClick={() => cancel(s.plan_code)}>
                      {s.status === 'pending_payment' ? 'Withdraw' : 'Cancel'}
                    </Button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </Card>

      {checkout && (
        <CheckoutModal
          plan={checkout.plan}
          cycle={checkout.cycle}
          payment={payment}
          busy={busyCode === checkout.plan.code}
          onConfirm={confirmSubscribe}
          onCancel={() => setCheckout(null)}
        />
      )}
    </div>
  );
}
