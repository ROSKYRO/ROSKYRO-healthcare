import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, StatTile, Button, PageLoading, formatCurrency } from '../../components/ui';

export default function InternalDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setError('');
    api.get('/dashboard/internal').then((res) => setData(res.data)).catch(() => {
      setError('Could not load the dashboard. Please try again.');
    });
  }, []);

  useEffect(load, [load]);

  if (error && !data) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!data) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">ROSKYRO Team Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">{user.name} · {user.role.replace(/^roskyro_/, '').replace(/_/g, ' ')}</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile label="Active Businesses" value={data.activeOrganizations} icon={"\u{1F3E5}"} tone="brand" />
        <StatTile label="Verified Partners" value={data.verifiedPartners} icon={"\u{1F91D}"} tone="blue" />
        <StatTile label="Pending Verifications" value={data.pendingPartnerVerifications} icon={"\u{1F510}"} tone="amber" />
        <StatTile label="Open Tasks" value={data.openTasks} sub={`${data.overdueTasks} overdue`} icon={"\u{1F4CB}"} tone={data.overdueTasks > 0 ? 'rose' : 'slate'} />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <CardHeader title="My Queue" action={<Link to="/team/tasks"><Button size="sm" variant="secondary">Open</Button></Link>} />
          <div className="px-5 pb-5 flex gap-8">
            <div>
              <p className="text-2xl font-bold text-gray-900">{data.myQueue.open}</p>
              <p className="text-xs text-gray-400">Open tasks assigned to me</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-rose-600">{data.myQueue.overdue}</p>
              <p className="text-xs text-gray-400">Overdue (SLA breached)</p>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader title="Pending Settlements" action={<Link to="/team/settlements"><Button size="sm" variant="secondary">Open</Button></Link>} />
          <div className="px-5 pb-5 flex gap-8">
            <div>
              <p className="text-2xl font-bold text-gray-900">{data.pendingSettlements.n}</p>
              <p className="text-xs text-gray-400">Awaiting payout</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">{formatCurrency(data.pendingSettlements.total)}</p>
              <p className="text-xs text-gray-400">Total value</p>
            </div>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader title="Referral Volume (Last 14 Days)" />
        <div className="px-5 pb-5">
          {data.referralVolumeLast14Days.length === 0 ? (
            <p className="text-sm text-gray-400">No referrals yet in this window.</p>
          ) : (
            (() => {
              const maxN = Math.max(1, ...data.referralVolumeLast14Days.map((d) => d.n));
              const MAX_BAR_PX = 100; // fits within the h-32 (128px) container with room for the label
              return (
                <div className="flex items-end gap-2 h-32">
                  {data.referralVolumeLast14Days.map((d) => (
                    <div key={d.day} className="flex-1 flex flex-col items-center justify-end gap-1" title={`${d.n} referral${d.n === 1 ? '' : 's'}`}>
                      <div className="w-full bg-brand-500 rounded-t" style={{ height: `${Math.max(4, Math.round((d.n / maxN) * MAX_BAR_PX))}px` }} />
                      <span className="text-[10px] text-gray-400">{d.day.slice(5)}</span>
                    </div>
                  ))}
                </div>
              );
            })()
          )}
        </div>
      </Card>
    </div>
  );
}
