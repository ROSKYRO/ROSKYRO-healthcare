import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../../lib/api';
import { Card, Table, Badge, Button, PageLoading, Select, formatDate } from '../../components/ui';

export default function ReferralsList({ title, subtitle, basePath, newPath, showCreate = false }) {
  const [referrals, setReferrals] = useState(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    setError('');
    // Previously no .catch -- this list is shared by all three shells
    // (customer/partner/internal referral pages), so a failure here left
    // every one of them stuck on a permanent spinner.
    api.get('/referrals', { params: status ? { status } : {} }).then((res) => setReferrals(res.data.referrals)).catch((err) => {
      setError(err?.response?.data?.error || 'Could not load referrals. Please try again.');
      setReferrals([]);
    });
  }, [status]);

  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!referrals) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
          <p className="text-sm text-gray-500 mt-1">{subtitle}</p>
        </div>
        {showCreate && <Link to={newPath}><Button>+ New Referral</Button></Link>}
      </div>

      <Card>
        <div className="px-5 pt-5 flex items-center gap-3">
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="max-w-[220px]">
            <option value="">All statuses</option>
            {['draft', 'pending_review', 'sent', 'accepted', 'declined', 'in_progress', 'report_uploaded', 'completed', 'cancelled'].map((s) => (
              <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
            ))}
          </Select>
        </div>
        <div className="pt-3">
          <Table
            emptyMessage="No referrals match this filter."
            rows={referrals}
            onRowClick={(r) => navigate(`${basePath}/${r.id}`)}
            columns={[
              { key: 'referral_code', header: 'Referral' },
              { key: 'patient_name', header: 'Patient' },
              { key: 'referring_org_name', header: 'From' },
              { key: 'partner_org_name', header: 'To Partner' },
              { key: 'service_requested', header: 'Service' },
              { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
              { key: 'created_at', header: 'Created', render: (r) => formatDate(r.created_at) },
            ]}
          />
        </div>
      </Card>
    </div>
  );
}
