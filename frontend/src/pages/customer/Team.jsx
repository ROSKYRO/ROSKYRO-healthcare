import { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../../context/AuthContext';
import api from '../../lib/api';
import { Card, Table, Badge, Button, Input, Select, PageLoading } from '../../components/ui';

export default function Team() {
  const { user } = useAuth();
  const [team, setTeam] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', role: 'staff', phone: '', password: '' });
  const [error, setError] = useState('');

  const [loadError, setLoadError] = useState('');

  const load = useCallback(() => {
    setLoadError('');
    api.get(`/orgs/${user.orgId}/team`).then((res) => setTeam(res.data.team)).catch(() => {
      setLoadError('Could not load your team. Please try again.');
    });
  }, [user.orgId]);

  useEffect(load, [load]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    try {
      await api.post(`/orgs/${user.orgId}/team`, form);
      setShowForm(false);
      setForm({ name: '', email: '', role: 'staff', phone: '', password: '' });
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not add team member.');
    }
  }

  if (loadError) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{loadError}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }
  if (!team) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">My Team</h1>
          <p className="text-sm text-gray-500 mt-1">Staff and doctors with access to {user.orgName}.</p>
        </div>
        <Button onClick={() => setShowForm((s) => !s)}>{showForm ? 'Close' : '+ Invite Team Member'}</Button>
      </div>

      {showForm && (
        <Card className="p-5">
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
            <Input label="Name" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            <Input label="Email" type="email" required value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
            <Select label="Role" value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}>
              <option value="staff">Staff</option>
              <option value="doctor">Doctor</option>
            </Select>
            <Input label="Mobile number" required value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} placeholder="98000 00002" />
            <Input label="Temporary password" type="password" required value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} />
            {error && <p className="text-sm text-rose-600 col-span-2">{error}</p>}
            <div className="col-span-2"><Button type="submit">Add to team</Button></div>
          </form>
        </Card>
      )}

      <Card>
        <Table
          rows={team}
          columns={[
            { key: 'name', header: 'Name' },
            { key: 'email', header: 'Email' },
            { key: 'role', header: 'Role', render: (r) => <Badge tone="slate">{r.role}</Badge> },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
          ]}
        />
      </Card>
    </div>
  );
}
