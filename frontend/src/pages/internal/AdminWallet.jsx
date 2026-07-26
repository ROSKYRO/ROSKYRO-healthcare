import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../lib/api';
import { Card, CardHeader, StatTile, Table, Badge, Input, PageLoading, formatCurrency } from '../../components/ui';

function currentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

export default function AdminWallet() {
  const { user } = useAuth();
  const [period, setPeriod] = useState(currentMonth());
  const [summary, setSummary] = useState(null);

  const load = useCallback(() => {
    if (user.role !== 'roskyro_admin') return;
    api.get('/settlements/admin-wallet', { params: { period } }).then((res) => setSummary(res.data));
  }, [period, user.role]);

  useEffect(load, [load]);

  if (user.role !== 'roskyro_admin') {
    return (
      <Card className="p-10 text-center max-w-md mx-auto">
        <p className="text-lg font-bold text-gray-900">Super admin access only</p>
        <p className="text-sm text-gray-500 mt-2">
          The consolidated Earnings Wallet is only visible to a ROSKYRO super admin account.
        </p>
      </Card>
    );
  }

  if (!summary) return <PageLoading />;

  const { subscription, marketing_fees: marketingFees, marketing_fee_payouts: payouts, wallet } = summary;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Earnings Wallet</h1>
          <p className="text-sm text-gray-500 mt-1">
            Ek hi jagah par ROSKYRO ke dono revenue streams: partners ki Marketing Fees aur businesses ki apni
            subscription renewal payments, is period ke liye — plus har business ko % ke hisab se kitna Marketing
            Fee Payout wapas bhejna hai. Ye calculation sirf is period ke liye hai — agla period naye sirey se
            (zero se) shuru hota hai, jab tak koi charge/settlement is period ke against generate na ho.
          </p>
        </div>
        <Input label="Period" type="month" value={period} onChange={(e) => setPeriod(e.target.value)} className="max-w-[160px]" />
      </div>

      <div className="grid md:grid-cols-3 gap-5">
        <StatTile label="Total collected this period" value={formatCurrency(wallet.total_collected_this_period)} icon={"\u{1F4B0}"} tone="brand" />
        <StatTile label="Already paid out to businesses" value={formatCurrency(wallet.already_paid_out_to_businesses)} icon={"\u{2705}"} tone="blue" />
        <StatTile label="Pending to send to businesses" value={formatCurrency(wallet.pending_to_send_to_businesses)} icon={"\u{23F3}"} tone="amber" />
      </div>

      <Card className="p-5">
        <p className="text-sm text-gray-500">Net wallet balance after payouts (collected − already paid − pending to send)</p>
        <p className="text-2xl font-bold text-gray-900">{formatCurrency(wallet.net_after_payouts)}</p>
      </Card>

      <div className="grid md:grid-cols-2 gap-5">
        <Card>
          <CardHeader
            title="Subscription Renewal Fees"
            subtitle="Businesses apne ROSKYRO plan ki renewal ke liye kitna owe karte hain, is period ke liye."
          />
          <div className="px-5 pb-5 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">Collected (confirmed)</span>
              <span className="font-semibold text-emerald-700">{formatCurrency(subscription.collected_amount)} · {subscription.collected_count}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">Awaiting ROSKYRO confirmation</span>
              <span className="font-semibold text-gray-900">{formatCurrency(subscription.awaiting_confirmation_amount)} · {subscription.awaiting_confirmation_count}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">Awaiting business payment</span>
              <span className="font-semibold text-gray-900">{formatCurrency(subscription.awaiting_payment_amount)} · {subscription.awaiting_payment_count}</span>
            </div>
            <div className="flex items-center justify-between text-sm border-t border-gray-100 pt-3">
              <span className="text-gray-500">Total charged</span>
              <span className="font-semibold text-gray-900">{formatCurrency(subscription.total_charged_amount)} · {subscription.total_charged_count}</span>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Marketing Fees (from Partners)"
            subtitle="Partners har completed referral ke liye ROSKYRO ko kitna owe karte hain, is period ke liye."
          />
          <div className="px-5 pb-5 space-y-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">Collected (confirmed)</span>
              <span className="font-semibold text-emerald-700">{formatCurrency(marketingFees.collected_amount)} · {marketingFees.collected_count}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">Awaiting ROSKYRO confirmation</span>
              <span className="font-semibold text-gray-900">{formatCurrency(marketingFees.awaiting_confirmation_amount)} · {marketingFees.awaiting_confirmation_count}</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-500">Awaiting partner payment</span>
              <span className="font-semibold text-gray-900">{formatCurrency(marketingFees.awaiting_payment_amount)} · {marketingFees.awaiting_payment_count}</span>
            </div>
            <div className="flex items-center justify-between text-sm border-t border-gray-100 pt-3">
              <span className="text-gray-500">Total charged</span>
              <span className="font-semibold text-gray-900">{formatCurrency(marketingFees.total_charged_amount)} · {marketingFees.total_charged_count}</span>
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="Marketing Fee Payouts — Business-wise"
          subtitle={`Fixed ${payouts.payout_percentage}% rate — jitna is period Marketing Fee collect hua unke referrals se, us business ko utna % wapas jaata hai.`}
        />
        <Table
          rows={payouts.businesses}
          keyField="org_id"
          emptyMessage="No referring businesses generated Marketing Fees this period."
          columns={[
            { key: 'org_name', header: 'Business' },
            { key: 'total_fees_collected', header: 'Fees Collected', render: (r) => formatCurrency(r.total_fees_collected) },
            { key: 'payout_amount', header: `Payout (${payouts.payout_percentage}%)`, render: (r) => formatCurrency(r.payout_amount) },
            { key: 'payout_status', header: 'Status', render: (r) => <Badge tone={r.payout_status === 'paid' ? 'paid' : r.payout_status === 'pending' ? 'pending' : 'slate'}>{r.payout_status.replace(/_/g, ' ')}</Badge> },
          ]}
        />
      </Card>
    </div>
  );
}
