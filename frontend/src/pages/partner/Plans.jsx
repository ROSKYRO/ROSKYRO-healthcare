import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import PricingCards from '../../components/PricingCards';
import AddonCard from '../../components/AddonCard';
import { Card, Badge, Button, PageLoading, formatCurrency, formatDate } from '../../components/ui';

// Pillar codes stay lowercase internally ('grow'/'manage'/'connect'), but
// 'connect' now displays as "Networking Marketing" everywhere in the UI.
const PILLAR_DISPLAY_NAMES = { grow: 'GROW', manage: 'MANAGE', connect: 'Networking Marketing' };

function CheckoutModal({ plan, cycle, payment, onConfirm, onCancel, busy }) {
  const [copied, setCopied] = useState(false);
  const price = cycle === 'yearly' ? plan.yearly_price : plan.monthly_price;

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

        <div className="mt-5 bg-gray-50 border border-gray-200 rounded-xl p-4">
          <p className="text-xs text-gray-400">Pay via UPI</p>
          <div className="flex items-center justify-between mt-1">
            <p className="text-lg font-bold text-gray-900">{payment.upi_id}</p>
            <Button size="sm" variant="secondary" onClick={copyUpi}>{copied ? 'Copied!' : 'Copy'}</Button>
          </div>
          <p className="text-sm text-gray-500 mt-3">{payment.payment_note}</p>
        </div>

        <div className="mt-6 flex items-center gap-3">
          <Button variant="secondary" className="flex-1" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button className="flex-1" onClick={onConfirm} disabled={busy}>{busy ? 'Activating…' : "I've Paid — Activate"}</Button>
        </div>
      </Card>
    </div>
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

  async function subscribeAddon(addon) {
    setError('');
    setAddonBusy(true);
    try {
      await api.post('/partner-plans/subscribe', { planCode: addon.code, billingCycle: 'monthly' });
      await refreshPillars();
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not add this add-on.');
    } finally {
      setAddonBusy(false);
    }
  }

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
          Subscriptions are activated via UPI payment — pick a plan below, you'll see the payment UPI ID
          before anything is charged.
        </p>
      </Card>

      {error && <p className="text-sm text-rose-600">{error}</p>}

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
          requiredPillarActive={mine.activePillars.includes(reelsAddon.requires_pillar)}
          busy={addonBusy}
          onSubscribe={() => subscribeAddon(reelsAddon)}
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
                    {' '}({s.billing_cycle === 'yearly' ? 'Annual Membership' : 'Monthly Subscription'}) · started {formatDate(s.started_at)}
                    {s.cancelled_at ? ` · cancelled ${formatDate(s.cancelled_at)}` : ''}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <Badge tone={s.status}>{s.status}</Badge>
                  {s.status === 'active' && (
                    <Button size="sm" variant="ghost" disabled={busyCode === s.plan_code} onClick={() => cancel(s.plan_code)}>Cancel</Button>
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
