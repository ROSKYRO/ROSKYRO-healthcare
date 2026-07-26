import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { Card, CardHeader, Table, Badge, Button, Input, EmptyState, PageLoading } from '../../components/ui';

// A partner's own pitch to a business it wants to work with -- "let me be
// your designated partner for my category." The business Accepts/Declines
// from its own "My Partners" page (customer/Partnerships.jsx). Nothing here
// restricts the open marketplace either way -- this is purely about landing
// the "★ Your Partner" shortcut on a business's quick-referral search.
export default function PartnerPartnerships() {
  const [q, setQ] = useState('');
  const [businesses, setBusinesses] = useState(null);
  const [requests, setRequests] = useState(null);
  const [busyOrgId, setBusyOrgId] = useState(null);
  const [error, setError] = useState('');

  const loadRequests = useCallback(() => {
    api.get('/partnerships/requests').then((res) => setRequests(res.data.requests));
  }, []);

  useEffect(loadRequests, [loadRequests]);

  useEffect(() => {
    setBusinesses(null);
    const t = setTimeout(() => {
      api.get('/orgs/directory', { params: { q: q || undefined } }).then((res) => setBusinesses(res.data.organizations));
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  // Requests come back sorted newest-first; keep only the newest one per
  // business so a re-request after a decline shows the fresh "pending"
  // status instead of the stale decided one (the first occurrence per
  // org_id in this iteration order is always the newest).
  const requestByOrgId = new Map();
  for (const r of requests || []) {
    if (!requestByOrgId.has(r.org_id)) requestByOrgId.set(r.org_id, r);
  }

  async function sendRequest(org) {
    setError('');
    setBusyOrgId(org.id);
    try {
      await api.post('/partnerships/requests', { orgId: org.id });
      loadRequests();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not send this request.');
    } finally {
      setBusyOrgId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Partnerships</h1>
        <p className="text-sm text-gray-500 mt-1">
          Kisi business ko apna designated partner banne ka request bhejo — accept hone par aap unki quick-referral search mein ★ top pe dikhoge. Aapki khud ki listing kisi ke liye blocked nahi hoti, chahe request pending ho ya na bheji ho.
        </p>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <Card className="p-5 space-y-3">
        <CardHeader title="Find a Business" subtitle="Sirf woh businesses dikhte hain jo referral bhej sakte hain (Clinic, Hospital, Eye Hospital)." />
        <Input placeholder="Search by name…" value={q} onChange={(e) => setQ(e.target.value)} />
        {!businesses ? (
          <PageLoading />
        ) : businesses.length === 0 ? (
          <EmptyState title="No businesses found." subtitle="Try a different search term." />
        ) : (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {businesses.map((b) => {
              const existing = requestByOrgId.get(b.id);
              return (
                <div key={b.id} className="flex items-center justify-between px-4 py-3 rounded-xl border border-gray-200">
                  <div>
                    <p className="font-medium text-gray-900">{b.name}</p>
                    <p className="text-xs text-gray-500">{b.city || 'City n/a'} · {b.businessType}</p>
                  </div>
                  {existing ? (
                    <Badge tone={existing.status}>{existing.status}</Badge>
                  ) : (
                    <Button size="sm" disabled={busyOrgId === b.id} onClick={() => sendRequest(b)}>
                      {busyOrgId === b.id ? 'Sending…' : 'Send Request'}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card>
        <CardHeader title="Requests Sent" />
        <Table
          rows={requests || []}
          columns={[
            { key: 'org_name', header: 'Business', render: (r) => r.org_name || '—' },
            { key: 'category_name', header: 'Category', render: (r) => r.category_name || '—' },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
          ]}
        />
      </Card>
    </div>
  );
}
