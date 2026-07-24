import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, Table, Button, Input, Textarea, Badge, PageLoading, formatCurrency, formatDate } from '../../components/ui';

// Plan codes stay lowercase internally ('grow'/'manage'/'connect'/'complete'),
// but 'connect' now displays as "Networking Marketing" -- a plain
// .toUpperCase() on the code would still read "CONNECT".
const PLAN_DISPLAY_NAMES = { grow: 'GROW', manage: 'MANAGE', connect: 'Networking Marketing', complete: 'ROSKYRO Complete' };

function PlanEditor({ plan, onSave, busy }) {
  const [form, setForm] = useState({
    name: plan.name,
    tagline: plan.tagline || '',
    monthly_price: plan.monthly_price,
    yearly_price: plan.yearly_price || '',
    badge: plan.badge || '',
    best_for: plan.best_for || '',
    customer_promise: plan.customer_promise || '',
    features: (plan.features || []).join('\n'),
  });
  const [dirty, setDirty] = useState(false);

  function set(key) {
    return (e) => {
      setForm((f) => ({ ...f, [key]: e.target.value }));
      setDirty(true);
    };
  }

  async function handleSave() {
    await onSave(plan.code, {
      name: form.name,
      tagline: form.tagline,
      monthly_price: Number(form.monthly_price),
      yearly_price: form.yearly_price === '' ? null : Number(form.yearly_price),
      badge: form.badge || null,
      best_for: form.best_for,
      customer_promise: form.customer_promise,
      features: form.features.split('\n').map((f) => f.trim()).filter(Boolean),
    });
    setDirty(false);
  }

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{plan.code}</p>
        {plan.is_bundle && <Badge tone="verified">Bundle</Badge>}
      </div>
      <div className="grid grid-cols-2 gap-4 mt-3">
        <Input label="Display name" value={form.name} onChange={set('name')} />
        <Input label="Badge (e.g. Most Popular)" value={form.badge} onChange={set('badge')} placeholder="leave blank for none" />
        <Input label="Monthly price (₹)" type="number" value={form.monthly_price} onChange={set('monthly_price')} />
        <Input label="Yearly price (₹)" type="number" value={form.yearly_price} onChange={set('yearly_price')} />
      </div>
      <Textarea label="Tagline" rows={2} className="mt-4" value={form.tagline} onChange={set('tagline')} />
      <Textarea label="Best for" rows={1} className="mt-4" value={form.best_for} onChange={set('best_for')} />
      <Textarea label="Customer promise" rows={2} className="mt-4" value={form.customer_promise} onChange={set('customer_promise')} />
      <Textarea label="Features (one per line)" rows={6} className="mt-4" value={form.features} onChange={set('features')} />
      <div className="mt-4 flex items-center justify-between">
        {form.monthly_price && form.yearly_price ? (
          <p className="text-xs text-gray-400">
            Annual works out to {Math.round((1 - Number(form.yearly_price) / (Number(form.monthly_price) * 12)) * 100)}% off monthly.
          </p>
        ) : <span />}
        <Button size="sm" disabled={!dirty || busy} onClick={handleSave}>{busy ? 'Saving…' : 'Save Changes'}</Button>
      </div>
    </Card>
  );
}

export default function PricingManagement() {
  const { user } = useAuth();
  const [plans, setPlans] = useState(null);
  const [payment, setPayment] = useState(null);
  const [subscriptions, setSubscriptions] = useState(null);
  const [paymentForm, setPaymentForm] = useState({ upiId: '', paymentNote: '' });
  const [marketingRate, setMarketingRate] = useState(null);
  const [marketingRateForm, setMarketingRateForm] = useState('');
  const [busyCode, setBusyCode] = useState(null);
  const [paymentBusy, setPaymentBusy] = useState(false);
  const [marketingRateBusy, setMarketingRateBusy] = useState(false);
  const [message, setMessage] = useState('');

  const load = useCallback(() => {
    Promise.all([
      api.get('/plans'), api.get('/settings/payment'), api.get('/plans/subscriptions'), api.get('/settlements/marketing-fee-rate'),
    ]).then(([p, s, sub, mr]) => {
      setPlans(p.data.plans);
      setPayment(s.data);
      setPaymentForm({ upiId: s.data.upi_id || '', paymentNote: s.data.payment_note || '' });
      setSubscriptions(sub.data.subscriptions);
      setMarketingRate(mr.data.percentage);
      setMarketingRateForm(String(mr.data.percentage));
    });
  }, []);

  useEffect(load, [load]);

  if (user.role !== 'roskyro_admin') {
    return (
      <Card className="p-10 text-center max-w-md mx-auto">
        <p className="text-lg font-bold text-gray-900">Super admin access only</p>
        <p className="text-sm text-gray-500 mt-2">
          Pricing and payment settings can only be changed by a ROSKYRO super admin account.
        </p>
      </Card>
    );
  }

  if (!plans || !payment || !subscriptions || marketingRate == null) return <PageLoading />;

  function renewalCell(sub) {
    if (sub.status !== 'active' || !sub.renewal_date) {
      return <span className="text-xs text-gray-400">—</span>;
    }
    const daysLeft = Math.ceil((new Date(sub.renewal_date) - new Date()) / 86400000);
    const tone = daysLeft <= 3 ? 'text-rose-600 font-semibold' : daysLeft <= 14 ? 'text-amber-600 font-medium' : 'text-gray-700';
    return (
      <span className={tone}>
        {formatDate(sub.renewal_date)} <span className="text-xs">({daysLeft <= 0 ? 'due now' : `in ${daysLeft}d`})</span>
      </span>
    );
  }

  async function savePlan(code, patch) {
    setBusyCode(code);
    setMessage('');
    try {
      await api.patch(`/plans/${code}`, patch);
      setMessage(`${PLAN_DISPLAY_NAMES[code] || code.toUpperCase()} updated.`);
      load();
    } catch (err) {
      setMessage(err?.response?.data?.error || 'Could not save this plan.');
    } finally {
      setBusyCode(null);
    }
  }

  async function savePayment(e) {
    e.preventDefault();
    setPaymentBusy(true);
    setMessage('');
    try {
      await api.patch('/settings/payment', paymentForm);
      setMessage('UPI payment details updated.');
      load();
    } catch (err) {
      setMessage(err?.response?.data?.error || 'Could not save payment settings.');
    } finally {
      setPaymentBusy(false);
    }
  }

  async function saveMarketingRate(e) {
    e.preventDefault();
    setMarketingRateBusy(true);
    setMessage('');
    try {
      await api.patch('/settlements/marketing-fee-rate', { percentage: Number(marketingRateForm) });
      setMessage('Marketing Fee Payout rate updated.');
      load();
    } catch (err) {
      setMessage(err?.response?.data?.error || 'Could not save the Marketing Fee Payout rate.');
    } finally {
      setMarketingRateBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Pricing & Payments</h1>
        <p className="text-sm text-gray-500 mt-1">
          Super admin only — change what GROW / MANAGE / Networking Marketing / Complete cost, and where customer
          payments are collected.
        </p>
      </div>

      {message && <p className="text-sm text-brand-700 bg-brand-50 border border-brand-100 rounded-lg px-4 py-2">{message}</p>}

      <Card>
        <CardHeader title="UPI Payment Collection" subtitle="Shown to every customer at the moment they activate a subscription" />
        <form onSubmit={savePayment} className="px-5 pb-5 space-y-4">
          <Input label="UPI ID" value={paymentForm.upiId} onChange={(e) => setPaymentForm((f) => ({ ...f, upiId: e.target.value }))} placeholder="roskyro@okhdfcbank" required />
          <Textarea
            label="Payment instructions shown to customers"
            rows={3}
            value={paymentForm.paymentNote}
            onChange={(e) => setPaymentForm((f) => ({ ...f, paymentNote: e.target.value }))}
          />
          <p className="text-xs text-gray-400">Last updated {payment.updated_at ? new Date(payment.updated_at).toLocaleString('en-IN') : '—'}</p>
          <Button type="submit" disabled={paymentBusy}>{paymentBusy ? 'Saving…' : 'Save UPI Settings'}</Button>
        </form>
      </Card>

      <Card>
        <CardHeader
          title="Marketing Fee Payout Rate"
          subtitle="Patient referrals ab marketing ki tarah treat hoti hain — partners jo Marketing Fee ROSKYRO ko pay karte hain, uska ye fixed % referring businesses (dr./clinic/hospital) ko periodic payout ke roop mein wapas jaata hai."
        />
        <form onSubmit={saveMarketingRate} className="px-5 pb-5 space-y-4">
          <Input
            label="Payout rate (%)"
            type="number" min="0" max="100" step="0.5"
            value={marketingRateForm}
            onChange={(e) => setMarketingRateForm(e.target.value)}
            required
          />
          <Button type="submit" disabled={marketingRateBusy}>{marketingRateBusy ? 'Saving…' : 'Save Payout Rate'}</Button>
        </form>
      </Card>

      <Card>
        <CardHeader
          title="Subscriptions & Renewals"
          subtitle="Every organization's subscription across the platform, with its next renewal date — there's no auto-renew job in v1, so this is what's due for billing follow-up."
        />
        <Table
          rows={subscriptions}
          emptyMessage="No subscriptions yet."
          columns={[
            { key: 'org_name', header: 'Business' },
            { key: 'plan_name', header: 'Plan', render: (r) => <span className="flex items-center gap-1.5">{r.plan_name}{r.is_bundle && <Badge tone="verified">Bundle</Badge>}</span> },
            { key: 'billing_cycle', header: 'Cycle', render: (r) => <Badge tone="slate">{r.billing_cycle}</Badge> },
            { key: 'price_at_purchase', header: 'Price', render: (r) => formatCurrency(r.price_at_purchase) },
            { key: 'started_at', header: 'Started', render: (r) => formatDate(r.started_at) },
            { key: 'renewal_date', header: 'Renewal Date', render: renewalCell },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
          ]}
        />
      </Card>

      <div>
        <h2 className="text-lg font-bold text-gray-900 mb-3">Pillar & Bundle Pricing</h2>
        <div className="grid md:grid-cols-2 gap-5">
          {plans.map((plan) => (
            <PlanEditor key={plan.code} plan={plan} onSave={savePlan} busy={busyCode === plan.code} />
          ))}
        </div>
      </div>
    </div>
  );
}
