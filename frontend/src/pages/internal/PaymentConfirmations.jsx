import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { Card, CardHeader, Table, Button, PageLoading, formatCurrency, formatDateTime } from '../../components/ui';

// One row per still-pending self-serve subscription CLAIM -- a business or
// partner said "I've paid" (see routers/plans.py's subscribe() / routers/
// partner_plans.py's subscribe_partner(), round 23), but the pillar stays
// locked until a roskyro_admin reviews the UPI payment and either confirms
// or rejects it here. Mirrors the internal Subscription Renewals page's
// mark-paid/confirm-received UX, just for the very FIRST billing period of
// a subscription instead of a later renewal (renewals have their own page,
// unchanged -- see SubscriptionRenewals.jsx).
function RequestsTable({ title, subtitle, rows, busyId, reasonDrafts, onSetReason, onConfirm, onReject }) {
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} />
      <Table
        rows={rows}
        emptyMessage="No pending payment requests right now."
        columns={[
          { key: 'org_name', header: 'Org' },
          { key: 'plan_name', header: 'Plan', render: (r) => (
            <div>
              <p>{r.plan_name}</p>
              <p className="text-xs text-gray-400">{r.billing_cycle}</p>
            </div>
          ) },
          { key: 'price_at_purchase', header: 'Amount', render: (r) => formatCurrency(r.price_at_purchase) },
          { key: 'requested_at', header: 'Submitted', render: (r) => formatDateTime(r.requested_at) },
          { key: 'payment_reference', header: 'Reference', render: (r) => r.payment_reference
            ? <span className="text-xs font-mono text-gray-600">{r.payment_reference}</span>
            : <span className="text-xs text-gray-400">Not provided</span> },
          { key: 'actions', header: '', render: (r) => (
            <div className="flex flex-col items-end gap-2 min-w-[220px]">
              <div className="flex items-center gap-2">
                <Button size="sm" disabled={busyId === r.id} onClick={() => onConfirm(r)}>
                  {busyId === r.id ? '…' : 'Confirm Payment'}
                </Button>
                <Button size="sm" variant="danger" disabled={busyId === r.id} onClick={() => onReject(r)}>
                  {busyId === r.id ? '…' : 'Reject'}
                </Button>
              </div>
              <input
                type="text"
                placeholder="Rejection reason (optional)"
                value={reasonDrafts[r.id] || ''}
                onChange={(e) => onSetReason(r.id, e.target.value)}
                className="text-xs border border-gray-200 rounded-lg px-2 py-1 w-full"
              />
            </div>
          ) },
        ]}
      />
    </Card>
  );
}

export default function PaymentConfirmations() {
  const [businessRows, setBusinessRows] = useState(null);
  const [partnerRows, setPartnerRows] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [reasonDrafts, setReasonDrafts] = useState({});
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setError('');
    Promise.all([api.get('/plans/subscriptions'), api.get('/partner-plans/subscriptions')])
      .then(([b, p]) => {
        setBusinessRows(b.data.subscriptions.filter((s) => s.status === 'pending_payment'));
        setPartnerRows(p.data.subscriptions.filter((s) => s.status === 'pending_payment'));
      })
      .catch(() => setError('Could not load pending payment requests. Please try again.'));
  }, []);

  useEffect(load, [load]);

  function setReason(id, value) {
    setReasonDrafts((d) => ({ ...d, [id]: value }));
  }

  async function confirm(row, endpoint) {
    setBusyId(row.id);
    setError('');
    try {
      await api.post(`${endpoint}/${row.id}/confirm-payment`);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not confirm this payment.');
    } finally {
      setBusyId(null);
    }
  }

  async function reject(row, endpoint) {
    setBusyId(row.id);
    setError('');
    try {
      await api.post(`${endpoint}/${row.id}/reject-payment`, { reason: reasonDrafts[row.id] || undefined });
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not reject this payment.');
    } finally {
      setBusyId(null);
    }
  }

  if (error && !businessRows && !partnerRows) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }
  if (!businessRows || !partnerRows) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Payment Confirmations</h1>
        <p className="text-sm text-gray-500 mt-1">
          Har naya subscription (business ya partner) ab UPI payment ke "I've Paid" claim ke baad turant active nahi
          hota — yahan se payment verify karke Confirm karo, tabhi wo pillar active hota hai. Reject karne se claim
          band ho jaata hai aur business/partner dobara try kar sakta hai.
        </p>
      </div>

      {error && <p className="text-sm text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-4 py-2">{error}</p>}

      <RequestsTable
        title="Business subscriptions"
        subtitle="GROW / MANAGE / Networking Marketing / Complete + add-ons, claimed by a business owner."
        rows={businessRows}
        busyId={busyId}
        reasonDrafts={reasonDrafts}
        onSetReason={setReason}
        onConfirm={(r) => confirm(r, '/plans')}
        onReject={(r) => reject(r, '/plans')}
      />

      <RequestsTable
        title="Partner subscriptions"
        subtitle="Same services, claimed by a partner admin on the partner-audience pricing."
        rows={partnerRows}
        busyId={busyId}
        reasonDrafts={reasonDrafts}
        onSetReason={setReason}
        onConfirm={(r) => confirm(r, '/partner-plans')}
        onReject={(r) => reject(r, '/partner-plans')}
      />
    </div>
  );
}
