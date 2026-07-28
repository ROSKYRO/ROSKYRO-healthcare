import { useEffect, useState } from 'react';
import api from '../../lib/api';
import { Card, Table, Badge, Button, PageLoading, formatDate, formatCurrency } from '../../components/ui';

const PILLAR_TONE = { grow: 'completed', manage: 'sent', connect: 'pending' };
const BUSINESS_CATEGORY_LABELS = { solo_doctor: 'Solo Doctor', clinic: 'Clinic', hospital: 'Hospital (All Category)' };

export default function Organizations() {
  const [orgs, setOrgs] = useState(null);
  const [error, setError] = useState('');

  const load = () => {
    setError('');
    api.get('/orgs').then((res) => setOrgs(res.data.organizations)).catch(() => {
      setError('Could not load businesses. Please try again.');
    });
  };

  useEffect(load, []);

  if (error) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }
  if (!orgs) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Businesses</h1>
        <p className="text-sm text-gray-500 mt-1">Every healthcare business onboarded onto ROSKYRO Healthcare OS.</p>
      </div>

      <Card>
        <Table
          rows={orgs}
          columns={[
            { key: 'name', header: 'Business' },
            { key: 'business_type', header: 'Type', render: (r) => <Badge tone="slate">{r.business_type.replace(/_/g, ' ')}</Badge> },
            { key: 'business_category', header: 'Category', render: (r) => r.business_category ? <Badge tone="slate">{BUSINESS_CATEGORY_LABELS[r.business_category] || r.business_category}</Badge> : <span className="text-xs text-gray-400">—</span> },
            { key: 'city', header: 'City' },
            {
              key: 'active_pillars',
              header: 'Active Pillars',
              render: (r) =>
                !r.active_pillars || r.active_pillars.length === 0 ? (
                  <span className="text-xs text-gray-400">None</span>
                ) : (
                  <div className="flex flex-wrap gap-1">
                    {r.active_pillars.map((p) => (
                      <Badge key={p} tone={PILLAR_TONE[p] || 'slate'}>{p}</Badge>
                    ))}
                  </div>
                ),
            },
            { key: 'monthly_total', header: 'Monthly Value', render: (r) => formatCurrency(r.monthly_total || 0) },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'visibility_score', header: 'Visibility Score' },
            { key: 'created_at', header: 'Onboarded', render: (r) => formatDate(r.created_at) },
          ]}
        />
      </Card>
    </div>
  );
}
