import { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, CardHeader, StatTile, Badge, PageLoading, Button } from '../../components/ui';

export default function PartnerDashboard() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setError('');
    api.get('/dashboard/partner').then((res) => setData(res.data)).catch(() => {
      setError('Could not load your dashboard. Please try again.');
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
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{user.orgName}</h1>
          <p className="text-sm text-gray-500 mt-1">Partner performance overview</p>
        </div>
        <Badge tone={data.partner.verification_status}>{data.partner.verification_status}</Badge>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile label="Incoming Requests" value={data.incomingRequests} icon={"\u{1F4E5}"} tone="brand" />
        <StatTile label="Pending Requests" value={data.pendingRequests} icon={"\u{23F3}"} tone="amber" />
        <StatTile label="Completed" value={data.completedRequests} icon={"\u{2705}"} tone="blue" />
        <StatTile label="Rating" value={data.partner.rating_avg > 0 ? `${data.partner.rating_avg} ★` : '—'} sub={`${data.partner.rating_count} reviews`} tone="slate" />
      </div>

      <Card>
        <CardHeader title="Referral Requests" subtitle="Accept, decline and manage incoming referrals" action={<Link to="/partner/requests"><Button size="sm" variant="secondary">Open queue</Button></Link>} />
        <div className="px-5 pb-5 text-sm text-gray-500">
          You have {data.pendingRequests} request(s) awaiting action.
        </div>
      </Card>
    </div>
  );
}
