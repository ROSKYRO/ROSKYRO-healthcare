import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { Card, CardHeader, Table, Badge, Button, Input, PageLoading, formatCurrency } from '../../components/ui';

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export default function MarketingPayouts() {
  const [period, setPeriod] = useState(currentMonth());
  const [report, setReport] = useState(null);
  const [busyOrgId, setBusyOrgId] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    // Fixed: a failed fetch used to silently render an EMPTY report
    // ({ businesses: [], payout_percentage: 0 }) with no error shown --
    // indistinguishable from "genuinely nothing to pay out this period".
    // An ops user could conclude there's nothing owed when the real cause
    // was a transient API failure, missing real payouts. Now a failure
    // surfaces a real error instead of faking an empty-but-successful load.
    setError('');
    api.get('/settlements/marketing-report', { params: { period } })
      .then((res) => setReport(res.data))
      .catch(() => setError('Could not load the Marketing Fee report. Please try again.'));
  }, [period]);

  useEffect(load, [load]);

  async function generatePayout(orgId) {
    setBusyOrgId(orgId);
    setError('');
    try {
      await api.post('/settlements/marketing-payouts', { orgId, period });
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not generate payout.');
    } finally {
      setBusyOrgId(null);
    }
  }

  async function markPaid(payoutId) {
    setBusyOrgId(payoutId);
    setError('');
    try {
      await api.patch(`/settlements/marketing-payouts/${payoutId}/mark-paid`);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not mark payout paid.');
    } finally {
      setBusyOrgId(null);
    }
  }

  async function downloadInvoice(payoutId, orgName) {
    setDownloadingId(payoutId);
    setError('');
    try {
      const res = await api.get(`/settlements/marketing-payouts/${payoutId}/invoice`, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `marketing-fee-invoice-${orgName.replace(/\s+/g, '-').toLowerCase()}-${period}.pdf`;
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

  if (error && !report) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!report) return <PageLoading />;

  const totalCollected = report.businesses.reduce((sum, b) => sum + Number(b.total_fees_collected), 0);
  const totalPayout = report.businesses.reduce((sum, b) => sum + Number(b.payout_amount), 0);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Marketing Fee Payouts</h1>
          <p className="text-sm text-gray-500 mt-1">
            Har referral karne wale business ki complete list, is period ke liye — kitna Marketing Fee partners ne
            ROSKYRO ko diya jo unke referrals se aaya, calculated payout amount ({report.payout_percentage}% fixed
            rate), aur payout account. Payout finalize karne ke baad us business ke liye invoice bhi generate ho jaata hai.
          </p>
        </div>
        <Input label="Period" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} className="max-w-[160px]" />
      </div>

      {error && <p className="text-sm text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-4 py-2">{error}</p>}

      <div className="grid md:grid-cols-2 gap-5">
        <Card className="p-5">
          <p className="text-sm text-gray-500">Total Marketing Fees collected this period</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(totalCollected)}</p>
        </Card>
        <Card className="p-5">
          <p className="text-sm text-gray-500">Total payout due to businesses ({report.payout_percentage}%)</p>
          <p className="text-2xl font-bold text-gray-900">{formatCurrency(totalPayout)}</p>
        </Card>
      </div>

      <Card>
        <CardHeader title="Referring Businesses — Complete Data" subtitle="One row per business, this period." />
        <Table
          rows={report.businesses}
          keyField="org_id"
          emptyMessage="No referring businesses generated Marketing Fees this period."
          columns={[
            { key: 'org_name', header: 'Business' },
            { key: 'business_type', header: 'Type', render: (r) => <Badge tone="slate">{(r.business_type || '—').replace(/_/g, ' ')}</Badge> },
            { key: 'referral_count', header: 'Referrals' },
            { key: 'total_fees_collected', header: 'Fees Collected', render: (r) => formatCurrency(r.total_fees_collected) },
            { key: 'payout_amount', header: 'Calculated Payout', render: (r) => formatCurrency(r.payout_amount) },
            { key: 'payout_account_upi_id', header: 'Send To (UPI)', render: (r) => r.payout_account_upi_id
              ? <span className="font-mono text-xs text-gray-700">{r.payout_account_upi_id}</span>
              : <span className="text-xs text-rose-500">Not set by business</span> },
            { key: 'payout_status', header: 'Status', render: (r) => <Badge tone={r.payout_status === 'paid' ? 'paid' : r.payout_status === 'pending' ? 'pending' : 'slate'}>{r.payout_status.replace(/_/g, ' ')}</Badge> },
            { key: 'actions', header: '', render: (r) => {
              if (r.payout_status === 'nothing_collected') return null;
              if (r.payout_status === 'not_generated') {
                return (
                  <Button size="sm" disabled={busyOrgId === r.org_id} onClick={() => generatePayout(r.org_id)}>
                    {busyOrgId === r.org_id ? 'Generating…' : 'Generate Payout'}
                  </Button>
                );
              }
              return (
                <div className="flex items-center gap-2">
                  {r.payout_status === 'pending' && (
                    <Button size="sm" disabled={busyOrgId === r.payout_id} onClick={() => markPaid(r.payout_id)}>
                      {busyOrgId === r.payout_id ? 'Marking…' : 'Mark Paid'}
                    </Button>
                  )}
                  <Button size="sm" variant="secondary" disabled={downloadingId === r.payout_id} onClick={() => downloadInvoice(r.payout_id, r.org_name)}>
                    {downloadingId === r.payout_id ? '…' : '⬇ Invoice'}
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
