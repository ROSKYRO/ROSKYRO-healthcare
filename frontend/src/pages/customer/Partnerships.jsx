import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../lib/api';
import { canCreateReferrals } from '../../lib/referralRights';
import { Card, CardHeader, Table, Badge, Button, Input, EmptyState, PageLoading } from '../../components/ui';

// "My Partners" -- a per-category designated partner, layered ON TOP of the
// fully-open partner marketplace (see ReferralNew.jsx's quick-flow search,
// which still shows every partner regardless -- this just highlights one).
// Any user in the business can view this page; only the owner can set/end a
// partnership or decide an incoming request (mirrors Team.jsx's invite
// restriction) -- the backend enforces this with a 403, the UI below just
// hides the action controls for a non-owner rather than showing buttons
// that would fail.
export default function Partnerships() {
  const { user } = useAuth();
  const isOwner = user.role === 'owner';

  const [categories, setCategories] = useState(null);
  const [partnerships, setPartnerships] = useState(null);
  const [requests, setRequests] = useState(null);

  const [pickerCategory, setPickerCategory] = useState(null);
  const [pickerQ, setPickerQ] = useState('');
  const [pickerResults, setPickerResults] = useState(null);

  const [busyKey, setBusyKey] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    api.get('/partners/categories').then((res) => setCategories(res.data.categories));
    api.get('/partnerships').then((res) => setPartnerships(res.data.partnerships));
    if (isOwner) {
      api.get('/partnerships/requests').then((res) => setRequests(res.data.requests)).catch(() => setRequests([]));
    } else {
      setRequests([]);
    }
  }, [isOwner]);

  useEffect(load, [load]);

  useEffect(() => {
    if (!pickerCategory) return;
    setPickerResults(null);
    const t = setTimeout(() => {
      api.get('/partners', { params: { category: pickerCategory.slug, q: pickerQ || undefined } })
        .then((res) => setPickerResults(res.data.partners));
    }, 300);
    return () => clearTimeout(t);
  }, [pickerCategory, pickerQ]);

  function openPicker(category) {
    setError('');
    setPickerCategory(category);
    setPickerQ('');
  }

  async function choosePartner(partner) {
    setError('');
    setBusyKey(partner.id);
    try {
      await api.post('/partnerships', { partnerId: partner.id });
      setPickerCategory(null);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not set this partnership.');
    } finally {
      setBusyKey(null);
    }
  }

  async function endPartnership(categoryId) {
    setError('');
    setBusyKey(categoryId);
    try {
      await api.post(`/partnerships/${categoryId}/end`);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not end this partnership.');
    } finally {
      setBusyKey(null);
    }
  }

  async function decideRequest(requestId, decision) {
    setError('');
    setBusyKey(requestId);
    try {
      await api.post(`/partnerships/requests/${requestId}/decide`, { decision });
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not update this request.');
    } finally {
      setBusyKey(null);
    }
  }

  if (!canCreateReferrals(user)) {
    return (
      <EmptyState
        title="My Partners is for referral-creating businesses."
        subtitle="Designated partners sirf un business types ke liye hain jo referral bhej sakte hain (Clinic, Hospital, Eye Hospital)."
      />
    );
  }

  if (!categories || !partnerships || requests === null) return <PageLoading />;

  const byCategoryId = new Map(partnerships.map((p) => [p.category_id, p]));
  const pendingRequests = requests.filter((r) => r.status === 'pending');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">My Partners</h1>
        <p className="text-sm text-gray-500 mt-1">
          Har category ke liye ek "apna partner" mark karo — Naya Referral ke quick search mein woh ★ ke saath sabse top pe dikhega. Baaki partners bhi hamesha poori list mein dikhte rahenge — kisi ko refer karne se roka nahi jaata.
        </p>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      {isOwner && pendingRequests.length > 0 && (
        <Card>
          <CardHeader title="Incoming Partnership Requests" subtitle="Partners jo aapke saath designated partner banna chahte hain." />
          <Table
            rows={pendingRequests}
            columns={[
              { key: 'partner_org_name', header: 'Partner', render: (r) => r.partner_org_name || '—' },
              { key: 'category_name', header: 'Category', render: (r) => r.category_name || '—' },
              {
                key: 'actions',
                header: '',
                render: (r) => (
                  <div className="flex gap-2 justify-end">
                    <Button size="sm" disabled={busyKey === r.id} onClick={() => decideRequest(r.id, 'accepted')}>
                      {busyKey === r.id ? '…' : 'Accept'}
                    </Button>
                    <Button size="sm" variant="secondary" disabled={busyKey === r.id} onClick={() => decideRequest(r.id, 'declined')}>
                      Decline
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        </Card>
      )}

      <Card>
        <CardHeader title="Designated Partner, Per Category" />
        <Table
          rows={categories}
          keyField="id"
          columns={[
            { key: 'name', header: 'Category' },
            {
              key: 'partner',
              header: 'My Partner',
              render: (c) => {
                const p = byCategoryId.get(c.id);
                if (!p) return <span className="text-sm text-gray-400">Not set</span>;
                return (
                  <div>
                    <p className="font-medium text-gray-900">{p.partner_org_name}</p>
                    <p className="text-xs text-gray-400 flex items-center gap-1.5 mt-0.5">
                      {p.partner_city || 'City n/a'} · <Badge tone={p.partner_verification_status}>{p.partner_verification_status}</Badge>
                    </p>
                  </div>
                );
              },
            },
            ...(isOwner
              ? [
                  {
                    key: 'actions',
                    header: '',
                    render: (c) => {
                      const p = byCategoryId.get(c.id);
                      return (
                        <div className="flex gap-2 justify-end">
                          <Button size="sm" variant="secondary" onClick={() => openPicker(c)}>
                            {p ? 'Change' : 'Choose partner'}
                          </Button>
                          {p && (
                            <Button size="sm" variant="danger" disabled={busyKey === c.id} onClick={() => endPartnership(c.id)}>
                              {busyKey === c.id ? '…' : 'End'}
                            </Button>
                          )}
                        </div>
                      );
                    },
                  },
                ]
              : []),
          ]}
        />
      </Card>

      {pickerCategory && (
        <Card className="p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-gray-900">Choose partner for {pickerCategory.name}</h3>
            <button type="button" className="text-sm text-gray-400 hover:text-gray-600" onClick={() => setPickerCategory(null)}>
              Close ✕
            </button>
          </div>
          <Input placeholder="Search by name…" value={pickerQ} onChange={(e) => setPickerQ(e.target.value)} />
          {!pickerResults ? (
            <PageLoading />
          ) : pickerResults.length === 0 ? (
            <EmptyState title="No partners found in this category." />
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {pickerResults.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  disabled={busyKey === p.id}
                  onClick={() => choosePartner(p)}
                  className="w-full text-left px-4 py-3 rounded-xl border border-gray-200 hover:border-brand-400 hover:bg-brand-50 flex items-center justify-between disabled:opacity-60"
                >
                  <div>
                    <p className="font-medium text-gray-900">{p.org_name}</p>
                    <p className="text-xs text-gray-500">{p.city || 'City n/a'}</p>
                  </div>
                  <span className="text-sm text-brand-700 font-medium">{busyKey === p.id ? 'Setting…' : 'Set as my partner →'}</span>
                </button>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
