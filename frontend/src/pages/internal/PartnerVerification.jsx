import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { Card, Badge, Button, Select, PageLoading, Textarea } from '../../components/ui';

export default function PartnerVerification() {
  const [partners, setPartners] = useState(null);
  const [filter, setFilter] = useState('pending');
  const [notes, setNotes] = useState({});
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    api.get('/partners').then((res) => setPartners(res.data.partners));
  }, []);

  useEffect(load, [load]);

  async function decide(id, decision) {
    setBusyId(id);
    try {
      await api.post(`/partners/${id}/verify`, { decision, note: notes[id] || '' });
      load();
    } finally {
      setBusyId(null);
    }
  }

  if (!partners) return <PageLoading />;
  const filtered = filter === 'all' ? partners : partners.filter((p) => p.verification_status === filter);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Partner Verification</h1>
        <p className="text-sm text-gray-500 mt-1">Review new partner applications before they can receive referrals unattended.</p>
      </div>

      <Select value={filter} onChange={(e) => setFilter(e.target.value)} className="max-w-[200px]">
        <option value="pending">Pending</option>
        <option value="verified">Verified</option>
        <option value="rejected">Rejected</option>
        <option value="all">All</option>
      </Select>

      <div className="space-y-4">
        {filtered.length === 0 && <Card className="p-8 text-center text-sm text-gray-400">No partners in this view.</Card>}
        {filtered.map((p) => (
          <Card key={p.id} className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-semibold text-gray-900">{p.org_name}</p>
                <p className="text-xs text-gray-400">{p.category_name} · {p.city}</p>
              </div>
              <Badge tone={p.verification_status}>{p.verification_status}</Badge>
            </div>
            <div className="grid grid-cols-3 gap-3 mt-3 text-sm text-gray-600">
              <p>Contact: {p.contact_person || '—'}</p>
              <p>Phone: {p.contact_phone || '—'}</p>
              <p>Turnaround: {p.turnaround_time || '—'}</p>
            </div>
            {p.verification_status === 'pending' && (
              <div className="mt-4">
                <Textarea placeholder="Verification note (optional)" rows={2} value={notes[p.id] || ''} onChange={(e) => setNotes((n) => ({ ...n, [p.id]: e.target.value }))} />
                <div className="flex gap-3 mt-3">
                  <Button size="sm" disabled={busyId === p.id} onClick={() => decide(p.id, 'verified')}>Verify</Button>
                  <Button size="sm" variant="danger" disabled={busyId === p.id} onClick={() => decide(p.id, 'rejected')}>Reject</Button>
                </div>
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
