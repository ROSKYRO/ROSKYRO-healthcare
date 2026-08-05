import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, Table, Badge, Button, Input, PageLoading, formatCurrency, formatDate, formatDateTime } from '../../components/ui';

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export default function SubscriptionRenewals() {
  const { user } = useAuth();
  const [period, setPeriod] = useState(currentMonth());
  const [renewals, setRenewals] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);
  const [error, setError] = useState('');
  const [lastGenerateResult, setLastGenerateResult] = useState(null);

  const load = useCallback(() => {
    // Fixed: a failed fetch used to silently render an EMPTY renewals list
    // with no error shown -- indistinguishable from "genuinely nothing due
    // this period", so real pending/awaiting-confirmation renewals could
    // go unnoticed on a transient API failure.
    setError('');
    api.get('/subscription-renewals', { params: { period } })
      .then((res) => setRenewals(res.data.renewals))
      .catch(() => setError('Could not load renewal charges. Please try again.'));
  }, [period]);

  useEffect(load, [load]);

  async function generateCharges() {
    setGenerating(true);
    setError('');
    setLastGenerateResult(null);
    try {
      const res = await api.post('/subscription-renewals/generate', { period });
      setLastGenerateResult(res.data);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not generate renewal charges.');
    } finally {
      setGenerating(false);
    }
  }

  async function markPaid(id) {
    setBusyId(id);
    setError('');
    try {
      await api.post(`/subscription-renewals/${id}/mark-paid`, {});
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not mark this renewal paid.');
    } finally {
      setBusyId(null);
    }
  }

  async function confirmReceived(id) {
    setBusyId(id);
    setError('');
    try {
      await api.post(`/subscription-renewals/${id}/confirm-received`);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not confirm receipt.');
    } finally {
      setBusyId(null);
    }
  }

  async function downloadInvoice(renewal) {
    setDownloadingId(renewal.id);
    setError('');
    try {
      const res = await api.get(`/subscription-renewals/${renewal.id}/invoice`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `${renewal.invoice_number}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError('Could not download this invoice. Please try again.');
    } finally {
      setDownloadingId(null);
    }
  }

  if (error && !renewals) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!renewals) return <PageLoading />;

  const totalCharged = renewals.reduce((sum, r) => sum + Number(r.amount), 0);
  const totalCollected = renewals.filter((r) => r.status === 'paid').reduce((sum, r) => sum + Number(r.amount), 0);
  const totalPending = renewals.filter((r) => r.status !== 'paid').reduce((sum, r) => sum + Number(r.amount), 0);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Subscription Renewals</h1>
          <p className="text-sm text-gray-500 mt-1">
            Har business ki apne ROSKYRO plan (GROW/MANAGE/CONNECT/Complete) ki renewal payment yahan track
            hoti hai — pehli billing period instant checkout se already activate ho chuki hoti hai, ye sirf 2nd
            period se aage ki genuine renewals cover karta hai. Ek period ke liye "Generate Renewal Charges" chalane
            se har due subscription ke liye ek pending charge ban jaata hai (dobara chalana safe hai, duplicate nahi
            banega). Normal flow two-sided hai: business khud "paid" mark karta hai, phir ROSKYRO internal team
            receipt confirm karti hai — tabhi status "paid" hota hai aur invoice generate hoti hai.
          </p>
        </div>
        <Input label="Period" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} className="max-w-[160px]" />
      </div>

      {error && <p className="text-sm text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-4 py-2">{error}</p>}

      <Card className="p-5 flex items-center justify-between flex-wrap gap-4">
        <div>
          <p className="text-sm text-gray-500">Generate every due renewal charge for {period}</p>
          {lastGenerateResult && (
            <p className="text-xs text-gray-400 mt-1">
              Last run: {lastGenerateResult.created} created, {lastGenerateResult.skipped} skipped (already due-checked
              or already generated).
            </p>
          )}
        </div>
        {/* Fixed: this button was shown to every internal role (the route
            is only gated to `allow={['internal']}`, any of 10 roles), but
            the backend's POST /subscription-renewals/generate is
            roskyro_admin-only -- so any of the other 9 roles (ops manager,
            growth expert, support executive, etc.) could see and click it,
            and it would always fail with a generic error. Now hidden for
            non-admins, mirroring PasswordRequests.jsx's existing pattern. */}
        {user.role === 'roskyro_admin' ? (
          <Button disabled={generating} onClick={generateCharges}>
            {generating ? 'Generating…' : 'Generate Renewal Charges'}
          </Button>
        ) : (
          <p className="text-xs text-gray-400">Only a ROSKYRO super admin can generate renewal charges.</p>
        )}
      </Card>

      <div className="grid md:grid-cols-3 gap-5">
        <Card className="p-5">
          <p className="text-sm text-gray-500">Total charged this period</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(totalCharged)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-gray-500">Collected (confirmed paid)</p>
          <p className="text-2xl font-bold text-emerald-700">{formatCurrency(totalCollected)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-gray-500">Pending (unpaid or awaiting confirmation)</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(totalPending)}</p>
        </Card>
      </div>

      <Card>
        <CardHeader title="Renewal Charges" subtitle="One row per active subscription due for renewal this period." />
        <Table
          rows={renewals}
          emptyMessage="No renewal charges for this period yet — use Generate Renewal Charges above."
          columns={[
            { key: 'org_name', header: 'Business' },
            { key: 'plan_name', header: 'Plan' },
            { key: 'due_date', header: 'Due', render: (r) => (r.due_date ? formatDate(r.due_date) : '—') },
            { key: 'billing_cycle', header: 'Cycle', render: (r) => <Badge tone="slate">{r.billing_cycle}</Badge> },
            { key: 'amount', header: 'Amount', render: (r) => formatCurrency(r.amount) },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'payer_marked_paid_at', header: 'Business claims paid', render: (r) => r.payer_marked_paid_at
              ? (
                <div>
                  <span className="text-xs text-gray-600">{formatDateTime(r.payer_marked_paid_at)}</span>
                  {r.payment_reference && <p className="text-xs text-gray-400 font-mono">Ref: {r.payment_reference}</p>}
                </div>
              )
              : <span className="text-xs text-gray-400">Not yet</span> },
            { key: 'created_at', header: 'Generated', render: (r) => formatDate(r.created_at) },
            { key: 'actions', header: '', render: (r) => (
              <div className="flex items-center gap-2">
                {r.status !== 'paid' && r.payer_marked_paid_at && (
                  <Button size="sm" disabled={busyId === r.id} onClick={() => confirmReceived(r.id)}>
                    {busyId === r.id ? 'Confirming…' : 'Confirm Received'}
                  </Button>
                )}
                {r.status !== 'paid' && !r.payer_marked_paid_at && (
                  <Button size="sm" variant="secondary" disabled={busyId === r.id} onClick={() => markPaid(r.id)}>
                    {busyId === r.id ? '…' : 'Mark Paid (override)'}
                  </Button>
                )}
                {r.status === 'paid' && (
                  <Button size="sm" variant="secondary" disabled={downloadingId === r.id} onClick={() => downloadInvoice(r)}>
                    {downloadingId === r.id ? '…' : `⬇ ${r.invoice_number}`}
                  </Button>
                )}
              </div>
            ) },
          ]}
        />
      </Card>
    </div>
  );
}
