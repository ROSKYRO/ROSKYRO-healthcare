import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { Card, Badge, Button, PageLoading, EmptyState, formatDate } from '../../components/ui';

export default function Approvals() {
  const [approvals, setApprovals] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setError('');
    api.get('/approvals').then((res) => setApprovals(res.data.approvals)).catch(() => {
      setError('Could not load approvals. Please try again.');
    });
  }, []);

  useEffect(load, [load]);

  async function decide(id, decision) {
    setBusyId(id);
    try {
      await api.post(`/approvals/${id}/decision`, { decision });
      load();
    } finally {
      setBusyId(null);
    }
  }

  if (error) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }
  if (!approvals) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Pending Approvals</h1>
        <p className="text-sm text-gray-500 mt-1">
          Everything here is AI-drafted and human-reviewed by your ROSKYRO team. Nothing publishes without your go-ahead.
        </p>
      </div>

      {approvals.length === 0 ? (
        <EmptyState title="Nothing to approve right now." subtitle="You're all caught up." />
      ) : (
        <div className="space-y-4">
          {approvals.map((a) => (
            <Card key={a.id} className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-semibold text-gray-900">{a.title}</p>
                  <p className="text-xs text-gray-400 mt-0.5 capitalize">{a.approval_type.replace(/_/g, ' ')} · prepared by {a.prepared_by_name || 'ROSKYRO team'} · {formatDate(a.created_at)}</p>
                </div>
                <Badge tone={a.status}>{a.status}</Badge>
              </div>
              {a.description && <p className="text-sm text-gray-600 mt-3">{a.description}</p>}
              {a.status === 'pending' && (
                <div className="flex gap-3 mt-4">
                  <Button size="sm" disabled={busyId === a.id} onClick={() => decide(a.id, 'approved')}>Approve</Button>
                  <Button size="sm" variant="secondary" disabled={busyId === a.id} onClick={() => decide(a.id, 'rejected')}>Request changes</Button>
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
