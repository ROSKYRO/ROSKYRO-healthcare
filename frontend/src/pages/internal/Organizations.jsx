import { useEffect, useState } from 'react';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { Card, Table, Badge, Button, Input, PageLoading, formatDate, formatCurrency } from '../../components/ui';
import { BUSINESS_CATEGORY_LABELS } from '../../lib/businessTaxonomy';

const PILLAR_TONE = { grow: 'completed', manage: 'sent', connect: 'pending' };

// Round 24: "business or partner ko active, deactive and delete karne ka
// option bhi super admin k dashboard pr ho na chahiye" -- this table already
// lists BOTH businesses and partners (organizations collection has both,
// see backend routers/orgs.py's list_orgs -- no is_partner filter), so the
// new actions column lives here rather than a separate page. The backend
// (POST /orgs/{id}/activate|deactivate, DELETE /orgs/{id}) already restricts
// these to roskyro_admin via require_roles -- this frontend check is just
// so other internal roles (ops manager, growth expert, etc, who can all see
// this page) don't see buttons that would just 403 for them.
function DeleteOrgModal({ org, busy, error, onCancel, onConfirm }) {
  const [typedName, setTypedName] = useState('');
  const matches = typedName.trim() === org.name;

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <Card className="max-w-md w-full p-6">
        <p className="text-xs font-semibold text-rose-600 uppercase tracking-wide">Permanently delete</p>
        <h3 className="text-lg font-bold text-gray-900 mt-1">{org.name}</h3>
        <p className="text-sm text-gray-500 mt-2">
          Ye action <span className="font-semibold text-rose-600">permanent</span> hai — is organization ka poora
          data (team accounts, appointments, patients, subscriptions, referrals, invoices, sab kuch) hamesha ke
          liye delete ho jayega. Wapas nahi laya ja sakta.
        </p>
        <div className="mt-4">
          <Input
            label={`Confirm karne ke liye organization ka naam type karein: "${org.name}"`}
            value={typedName}
            onChange={(e) => setTypedName(e.target.value)}
            placeholder={org.name}
          />
        </div>
        {error && <p className="text-sm text-rose-600 mt-3">{error}</p>}
        <div className="mt-5 flex items-center gap-3">
          <Button variant="secondary" className="flex-1" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button variant="danger" className="flex-1" disabled={busy || !matches} onClick={onConfirm}>
            {busy ? 'Deleting…' : 'Delete Permanently'}
          </Button>
        </div>
      </Card>
    </div>
  );
}

// Round 25: "growth hub me esa link section add karde jisse business apne
// sare platform ... kuch ek hi jagah se dekh ske ki kya progress hai" -- the
// business's own Growth Hub / Dashboard now shows quick links out to its
// Google Business Profile, social accounts, website etc. ROSKYRO's internal
// team maintains these on the business's behalf (backend: PUT
// /orgs/{org_id}/platform-links, require_internal -- any internal role, not
// just super admin, unlike the destructive round-24 lifecycle actions
// below), so this "Edit Links" action is visible to every internal viewer
// of this page.
function PlatformLinksModal({ org, busy, error, onCancel, onSave }) {
  const [rows, setRows] = useState(
    org.platform_links && org.platform_links.length > 0
      ? org.platform_links.map((l) => ({ label: l.label, url: l.url }))
      : [{ label: '', url: '' }]
  );

  function updateRow(i, field, value) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)));
  }
  function addRow() {
    setRows((prev) => [...prev, { label: '', url: '' }]);
  }
  function removeRow(i) {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <Card className="max-w-lg w-full p-6 max-h-[90vh] overflow-y-auto">
        <p className="text-xs font-semibold text-brand-600 uppercase tracking-wide">Platform links</p>
        <h3 className="text-lg font-bold text-gray-900 mt-1">{org.name}</h3>
        <p className="text-sm text-gray-500 mt-2">
          Google Business Profile, social media, website — jo bhi links yahan set karoge, wo is business ke
          Growth Hub aur Dashboard par direct dikhenge.
        </p>
        <div className="mt-4 space-y-3">
          {rows.map((row, i) => (
            <div key={i} className="flex items-start gap-2">
              <div className="flex-1 space-y-2">
                <Input
                  placeholder="Label — jaise Google Business Profile"
                  value={row.label}
                  onChange={(e) => updateRow(i, 'label', e.target.value)}
                />
                <Input
                  placeholder="https://..."
                  value={row.url}
                  onChange={(e) => updateRow(i, 'url', e.target.value)}
                />
              </div>
              <Button size="sm" variant="ghost" className="mt-1" onClick={() => removeRow(i)} disabled={rows.length === 1}>
                ✕
              </Button>
            </div>
          ))}
        </div>
        <Button size="sm" variant="secondary" className="mt-3" onClick={addRow}>+ Add link</Button>
        {error && <p className="text-sm text-rose-600 mt-3">{error}</p>}
        <div className="mt-5 flex items-center gap-3">
          <Button variant="secondary" className="flex-1" onClick={onCancel} disabled={busy}>Cancel</Button>
          <Button
            className="flex-1"
            disabled={busy}
            onClick={() => onSave(rows.map((r) => ({ label: r.label.trim(), url: r.url.trim() })).filter((r) => r.label || r.url))}
          >
            {busy ? 'Saving…' : 'Save Links'}
          </Button>
        </div>
      </Card>
    </div>
  );
}

export default function Organizations() {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === 'roskyro_admin';
  const [orgs, setOrgs] = useState(null);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null); // org row
  const [deleteError, setDeleteError] = useState('');
  const [linksTarget, setLinksTarget] = useState(null); // org row
  const [linksBusy, setLinksBusy] = useState(false);
  const [linksError, setLinksError] = useState('');

  const load = () => {
    setError('');
    api.get('/orgs').then((res) => setOrgs(res.data.organizations)).catch(() => {
      setError('Could not load businesses. Please try again.');
    });
  };

  useEffect(load, []);

  async function toggleSuspend(org) {
    setBusyId(org.id);
    setError('');
    try {
      await api.post(`/orgs/${org.id}/${org.is_suspended ? 'activate' : 'deactivate'}`);
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not update this organization.');
    } finally {
      setBusyId(null);
    }
  }

  async function saveLinks(links) {
    if (!linksTarget) return;
    setLinksBusy(true);
    setLinksError('');
    try {
      await api.put(`/orgs/${linksTarget.id}/platform-links`, { links });
      setLinksTarget(null);
      load();
    } catch (err) {
      setLinksError(err?.response?.data?.error || 'Could not save these links.');
    } finally {
      setLinksBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setBusyId(deleteTarget.id);
    setDeleteError('');
    try {
      await api.delete(`/orgs/${deleteTarget.id}`, { data: { confirmName: deleteTarget.name } });
      setDeleteTarget(null);
      load();
    } catch (err) {
      setDeleteError(err?.response?.data?.error || 'Could not delete this organization.');
    } finally {
      setBusyId(null);
    }
  }

  if (error && !orgs) {
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
        <p className="text-sm text-gray-500 mt-1">
          Every healthcare business and partner onboarded onto ROSKYRO Healthcare OS.
          {isSuperAdmin && ' Activate, deactivate ya permanently delete kar sakte hain — sirf super admin ke paas ye right hai.'}
        </p>
      </div>

      {error && <p className="text-sm text-rose-600 bg-rose-50 border border-rose-100 rounded-lg px-4 py-2">{error}</p>}

      <Card>
        <Table
          rows={orgs}
          columns={[
            { key: 'name', header: 'Business' },
            { key: 'is_partner', header: 'Account Type', render: (r) => <Badge tone={r.is_partner ? 'sent' : 'slate'}>{r.is_partner ? 'Partner' : 'Business'}</Badge> },
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
            {
              key: 'status', header: 'Status', render: (r) => (
                r.is_suspended
                  ? <Badge tone="suspended">Suspended</Badge>
                  : <Badge tone={r.status}>{r.status}</Badge>
              ),
            },
            { key: 'visibility_score', header: 'Visibility Score' },
            { key: 'created_at', header: 'Onboarded', render: (r) => formatDate(r.created_at) },
            {
              key: 'platform_links', header: 'Platform Links', render: (r) => (
                <Button size="sm" variant="secondary" onClick={() => { setLinksTarget(r); setLinksError(''); }}>
                  {r.platform_links && r.platform_links.length > 0 ? `Edit Links (${r.platform_links.length})` : 'Add Links'}
                </Button>
              ),
            },
            ...(isSuperAdmin ? [{
              key: 'actions', header: '', render: (r) => (
                <div className="flex items-center gap-2 justify-end min-w-[220px]">
                  <Button size="sm" variant="secondary" disabled={busyId === r.id} onClick={() => toggleSuspend(r)}>
                    {busyId === r.id ? '…' : r.is_suspended ? 'Activate' : 'Deactivate'}
                  </Button>
                  <Button size="sm" variant="danger" disabled={busyId === r.id} onClick={() => { setDeleteTarget(r); setDeleteError(''); }}>
                    Delete
                  </Button>
                </div>
              ),
            }] : []),
          ]}
        />
      </Card>

      {deleteTarget && (
        <DeleteOrgModal
          org={deleteTarget}
          busy={busyId === deleteTarget.id}
          error={deleteError}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={confirmDelete}
        />
      )}

      {linksTarget && (
        <PlatformLinksModal
          org={linksTarget}
          busy={linksBusy}
          error={linksError}
          onCancel={() => setLinksTarget(null)}
          onSave={saveLinks}
        />
      )}
    </div>
  );
}
