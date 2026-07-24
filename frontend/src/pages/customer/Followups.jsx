import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, Table, Badge, Button, Input, Select, Textarea, PageLoading, formatDate } from '../../components/ui';

export default function Followups() {
  const [followups, setFollowups] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [status, setStatus] = useState('pending');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ patientName: '', patientPhone: '', reason: '', dueDate: '', notes: '' });
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    api.get('/followups', { params: status ? { status } : {} })
      .then((res) => setFollowups(res.data.followups))
      .catch((err) => { if (err?.response?.status === 402) setBlocked(true); });
  }, [status]);

  useEffect(load, [load]);

  async function handleSubmit(e) {
    e.preventDefault();
    await api.post('/followups', form);
    setShowForm(false);
    setForm({ patientName: '', patientPhone: '', reason: '', dueDate: '', notes: '' });
    load();
  }

  async function markDone(id) {
    setBusyId(id);
    try {
      await api.patch(`/followups/${id}`, { status: 'done' });
      load();
    } finally {
      setBusyId(null);
    }
  }

  if (blocked) return <UpgradePrompt pillar="manage" />;
  if (!followups) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Follow-up System</h1>
          <p className="text-sm text-gray-500 mt-1">Never lose track of a patient who needs a check-in.</p>
        </div>
        <Button onClick={() => setShowForm((s) => !s)}>{showForm ? 'Close' : '+ New Follow-up'}</Button>
      </div>

      {showForm && (
        <Card className="p-5">
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
            <Input label="Patient name" required value={form.patientName} onChange={(e) => setForm((f) => ({ ...f, patientName: e.target.value }))} />
            <Input label="Patient phone" value={form.patientPhone} onChange={(e) => setForm((f) => ({ ...f, patientPhone: e.target.value }))} />
            <Input label="Reason" required value={form.reason} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} placeholder="Post-surgery check" />
            <Input label="Due date" type="date" required value={form.dueDate} onChange={(e) => setForm((f) => ({ ...f, dueDate: e.target.value }))} />
            <Textarea label="Notes" rows={2} className="col-span-2" value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
            <div className="col-span-2"><Button type="submit">Save Follow-up</Button></div>
          </form>
        </Card>
      )}

      <Select value={status} onChange={(e) => setStatus(e.target.value)} className="max-w-[200px]">
        <option value="">All</option>
        <option value="pending">Pending</option>
        <option value="contacted">Contacted</option>
        <option value="done">Done</option>
        <option value="missed">Missed</option>
      </Select>

      <Card>
        <Table
          rows={followups}
          emptyMessage="No follow-ups in this view."
          columns={[
            { key: 'patient_name', header: 'Patient' },
            { key: 'reason', header: 'Reason' },
            { key: 'due_date', header: 'Due', render: (r) => formatDate(r.due_date) },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'actions', header: '', render: (r) => r.status !== 'done' && (
              <Button size="sm" disabled={busyId === r.id} onClick={() => markDone(r.id)}>Mark Done</Button>
            ) },
          ]}
        />
      </Card>
    </div>
  );
}
