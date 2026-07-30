import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import { Card, Table, Badge, Button, Input, Select, PageLoading } from '../../components/ui';

// Display labels for the fixed internal role registry (app/utils/roles.py's
// ROSKYRO_ROLES on the backend) -- kept in the same order as that list so
// this dropdown and the backend's validation error message ("role must be
// one of: ...") always read in the same order.
const ROLE_OPTIONS = [
  { value: 'roskyro_admin', label: 'Admin' },
  { value: 'roskyro_ops_manager', label: 'Ops Manager' },
  { value: 'roskyro_growth_expert', label: 'Growth Expert' },
  { value: 'roskyro_content_specialist', label: 'Content Specialist' },
  { value: 'roskyro_seo_specialist', label: 'SEO Specialist' },
  { value: 'roskyro_gbp_specialist', label: 'GBP Specialist' },
  { value: 'roskyro_review_manager', label: 'Review Manager' },
  { value: 'roskyro_crm_executive', label: 'CRM Executive' },
  { value: 'roskyro_support_executive', label: 'Support Executive' },
  { value: 'roskyro_quality_reviewer', label: 'Quality Reviewer' },
];

const roleLabel = (role) => ROLE_OPTIONS.find((r) => r.value === role)?.label || role;

const EMPTY_ADD_FORM = { name: '', email: '', phone: '', role: 'roskyro_support_executive', password: '' };

export default function ManageTeam() {
  const [members, setMembers] = useState(null);
  const [loadError, setLoadError] = useState('');

  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState(EMPTY_ADD_FORM);
  const [addError, setAddError] = useState('');
  const [saving, setSaving] = useState(false);

  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [editError, setEditError] = useState('');

  const load = useCallback(() => {
    setLoadError('');
    api.get('/team-members').then((res) => setMembers(res.data.members)).catch(() => {
      setLoadError('Could not load the team. Please try again.');
    });
  }, []);

  useEffect(load, [load]);

  async function handleAdd(e) {
    e.preventDefault();
    if (saving) return;
    setAddError('');
    setSaving(true);
    try {
      await api.post('/team-members', addForm);
      setShowAddForm(false);
      setAddForm(EMPTY_ADD_FORM);
      load();
    } catch (err) {
      setAddError(err?.response?.data?.error || 'Could not add this team member.');
    } finally {
      setSaving(false);
    }
  }

  function startEdit(member) {
    setEditingId(member.id);
    setEditError('');
    setEditForm({
      name: member.name || '', email: member.email || '', phone: member.phone || '',
      role: member.role, status: member.status || 'active', newPassword: '',
    });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditForm(null);
    setEditError('');
  }

  async function handleEditSave(e) {
    e.preventDefault();
    if (saving) return;
    setEditError('');
    setSaving(true);
    try {
      const body = { ...editForm };
      if (!body.newPassword) delete body.newPassword;
      await api.patch(`/team-members/${editingId}`, body);
      cancelEdit();
      load();
    } catch (err) {
      setEditError(err?.response?.data?.error || 'Could not save these changes.');
    } finally {
      setSaving(false);
    }
  }

  async function toggleStatus(member) {
    setLoadError('');
    try {
      await api.patch(`/team-members/${member.id}`, {
        status: member.status === 'active' ? 'inactive' : 'active',
      });
      load();
    } catch (err) {
      setLoadError(err?.response?.data?.error || `Could not update ${member.name}'s status.`);
    }
  }

  if (loadError && !members) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{loadError}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }
  if (!members) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Manage Team</h1>
          <p className="text-sm text-gray-500 mt-1">
            Add, edit or deactivate ROSKYRO's own internal team members (Team Roster's names/roles come from here).
          </p>
        </div>
        <Button onClick={() => { setShowAddForm((s) => !s); cancelEdit(); }}>
          {showAddForm ? 'Close' : '+ Add Team Member'}
        </Button>
      </div>

      {showAddForm && (
        <Card className="p-5">
          <form onSubmit={handleAdd} className="grid grid-cols-2 gap-4">
            <Input label="Name" required value={addForm.name} onChange={(e) => setAddForm((f) => ({ ...f, name: e.target.value }))} />
            <Input label="Email" type="email" required value={addForm.email} onChange={(e) => setAddForm((f) => ({ ...f, email: e.target.value }))} />
            <Select label="Role" value={addForm.role} onChange={(e) => setAddForm((f) => ({ ...f, role: e.target.value }))}>
              {ROLE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </Select>
            <Input label="Mobile number" required value={addForm.phone} onChange={(e) => setAddForm((f) => ({ ...f, phone: e.target.value }))} placeholder="98000 00002" />
            <Input label="Temporary password" type="password" required value={addForm.password} onChange={(e) => setAddForm((f) => ({ ...f, password: e.target.value }))} />
            {addError && <p className="text-sm text-rose-600 col-span-2">{addError}</p>}
            <div className="col-span-2"><Button type="submit" disabled={saving}>{saving ? 'Adding…' : 'Add to team'}</Button></div>
          </form>
        </Card>
      )}

      {editingId && editForm && (
        <Card className="p-5 border-brand-300">
          <p className="text-xs font-semibold text-brand-600 uppercase tracking-wide mb-3">Editing team member</p>
          <form onSubmit={handleEditSave} className="grid grid-cols-2 gap-4">
            <Input label="Name" required value={editForm.name} onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))} />
            <Input label="Email" type="email" required value={editForm.email} onChange={(e) => setEditForm((f) => ({ ...f, email: e.target.value }))} />
            <Select label="Role" value={editForm.role} onChange={(e) => setEditForm((f) => ({ ...f, role: e.target.value }))}>
              {ROLE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </Select>
            <Select label="Status" value={editForm.status} onChange={(e) => setEditForm((f) => ({ ...f, status: e.target.value }))}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
            <Input label="Mobile number" required value={editForm.phone} onChange={(e) => setEditForm((f) => ({ ...f, phone: e.target.value }))} />
            <Input
              label="Reset password (optional)" type="password" placeholder="Leave blank to keep current password"
              value={editForm.newPassword} onChange={(e) => setEditForm((f) => ({ ...f, newPassword: e.target.value }))}
            />
            {editError && <p className="text-sm text-rose-600 col-span-2">{editError}</p>}
            <div className="col-span-2 flex items-center gap-3">
              <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save changes'}</Button>
              <Button type="button" variant="secondary" onClick={cancelEdit} disabled={saving}>Cancel</Button>
            </div>
          </form>
        </Card>
      )}

      {loadError && <p className="text-sm text-rose-600">{loadError}</p>}

      <Card>
        <Table
          rows={members}
          emptyMessage="No internal team members yet."
          columns={[
            { key: 'name', header: 'Name' },
            { key: 'email', header: 'Email' },
            { key: 'phone', header: 'Phone' },
            { key: 'role', header: 'Role', render: (r) => <Badge tone="slate">{roleLabel(r.role)}</Badge> },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'actions', header: '', render: (r) => (
              <div className="flex items-center gap-2 justify-end">
                <Button size="sm" variant="secondary" onClick={() => { startEdit(r); setShowAddForm(false); }}>Edit</Button>
                <Button
                  size="sm"
                  variant={r.status === 'active' ? 'danger' : 'secondary'}
                  onClick={() => toggleStatus(r)}
                >
                  {r.status === 'active' ? 'Deactivate' : 'Reactivate'}
                </Button>
              </div>
            ) },
          ]}
        />
      </Card>
    </div>
  );
}
