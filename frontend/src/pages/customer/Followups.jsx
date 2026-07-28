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
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setError('');
    api.get('/followups', { params: status ? { status } : {} })
      .then((res) => setFollowups(res.data.followups))
      .catch((err) => {
        if (err?.response?.status === 402) setBlocked(true);
        else setError('Could not load follow-ups. Please try again.');
      });
  }, [status]);

  useEffect(load, [load]);

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      await api.post('/followups', form);
      setShowForm(false);
      setForm({ patientName: '', patientPhone: '', reason: '', dueDate: '', notes: '' });
      load();
    } catch (err) {
      setFormError(err?.response?.data?.error || 'Could not save this follow-up. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  async function markDone(id) {
    setBusyId(id);
    setError('');
    try {
      await api.patch(`/followups/${id}`, { status: 'done' });
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not mark this follow-up done. Please try again.');
    } finally {
      setBusyId(null);
    }
  }

  if (blocked) return <UpgradePrompt pillar="manage" />;

  if (error && !followups) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

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
            {formError && <p className="text-sm text-rose-600 col-span-2">{formError}</p>}
            <div className="col-span-2"><Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save Follow-up'}</Button></div>
          </form>
        </Card>
      )}

      {error && <p className="text-sm text-rose-600">{error}</p>}

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
