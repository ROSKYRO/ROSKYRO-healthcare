import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, Table, Badge, Button, Input, Textarea, PageLoading, formatDate, formatCurrency } from '../../components/ui';

export default function Patients() {
  const [patients, setPatients] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [q, setQ] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: '', phone: '', email: '', age: '', gender: '', notes: '' });
  const navigate = useNavigate();

  const load = useCallback(() => {
    api.get('/patients', { params: q ? { q } : {} })
      .then((res) => setPatients(res.data.patients))
      .catch((err) => { if (err?.response?.status === 402) setBlocked(true); });
  }, [q]);

  useEffect(load, [load]);

  async function handleSubmit(e) {
    e.preventDefault();
    await api.post('/patients', { ...form, age: form.age ? Number(form.age) : undefined });
    setShowForm(false);
    setForm({ name: '', phone: '', email: '', age: '', gender: '', notes: '' });
    load();
  }

  if (blocked) return <UpgradePrompt pillar="manage" />;
  if (!patients) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Patient CRM</h1>
          <p className="text-sm text-gray-500 mt-1">Every patient relationship in one place.</p>
        </div>
        <Button onClick={() => setShowForm((s) => !s)}>{showForm ? 'Close' : '+ Add Patient'}</Button>
      </div>

      {showForm && (
        <Card className="p-5">
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
            <Input label="Name" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
            <Input label="Phone" value={form.phone} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} />
            <Input label="Email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
            <Input label="Age" type="number" value={form.age} onChange={(e) => setForm((f) => ({ ...f, age: e.target.value }))} />
            <Textarea label="Notes" rows={2} className="col-span-2" value={form.notes} onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))} />
            <div className="col-span-2"><Button type="submit">Save Patient</Button></div>
          </form>
        </Card>
      )}

      <Input placeholder="Search by name or phone…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" />

      <Card>
        <Table
          rows={patients}
          onRowClick={(p) => navigate(`/app/patients/${p.id}`)}
          emptyMessage="No patients yet."
          columns={[
            { key: 'name', header: 'Name' },
            { key: 'phone', header: 'Phone' },
            { key: 'age', header: 'Age/Gender', render: (r) => `${r.age || '—'} ${r.gender || ''}` },
            { key: 'tags', header: 'Tags', render: (r) => (r.tags || []).map((t) => <Badge key={t} tone="slate">{t}</Badge>) },
            { key: 'last_visit_at', header: 'Last Visit', render: (r) => formatDate(r.last_visit_at) },
            { key: 'lifetime_value', header: 'Lifetime Value', render: (r) => formatCurrency(r.lifetime_value) },
          ]}
        />
      </Card>
    </div>
  );
}
