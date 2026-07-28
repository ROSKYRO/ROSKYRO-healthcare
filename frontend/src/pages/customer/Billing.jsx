import { useEffect, useState, useCallback } from 'react';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, Table, Badge, Button, Input, PageLoading, formatCurrency, formatDate } from '../../components/ui';

const emptyItem = { description: '', quantity: 1, unitPrice: '' };

export default function Billing() {
  const [invoices, setInvoices] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ patientName: '', patientPhone: '', dueDate: '' });
  const [items, setItems] = useState([{ ...emptyItem }]);
  const [busyId, setBusyId] = useState(null);
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    setError('');
    api.get('/billing').then((res) => setInvoices(res.data.invoices)).catch((err) => {
      if (err?.response?.status === 402) setBlocked(true);
      else setError('Could not load invoices. Please try again.');
    });
  }, []);

  useEffect(load, [load]);

  function updateItem(i, key, value) {
    setItems((its) => its.map((it, idx) => (idx === i ? { ...it, [key]: value } : it)));
  }

  const total = items.reduce((sum, it) => sum + Number(it.quantity || 0) * Number(it.unitPrice || 0), 0);

  async function handleSubmit(e) {
    e.preventDefault();
    const lineItems = items.filter((it) => it.description && it.unitPrice).map((it) => ({ ...it, quantity: Number(it.quantity) || 1, unitPrice: Number(it.unitPrice) }));
    if (!lineItems.length) return;
    setFormError('');
    setSaving(true);
    try {
      await api.post('/billing', { ...form, lineItems });
      setShowForm(false);
      setForm({ patientName: '', patientPhone: '', dueDate: '' });
      setItems([{ ...emptyItem }]);
      load();
    } catch (err) {
      setFormError(err?.response?.data?.error || 'Could not create this invoice. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  async function markPaid(id) {
    setBusyId(id);
    setError('');
    try {
      await api.patch(`/billing/${id}`, { status: 'paid' });
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not mark this invoice paid. Please try again.');
    } finally {
      setBusyId(null);
    }
  }

  if (blocked) return <UpgradePrompt pillar="manage" />;

  if (error && !invoices) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }

  if (!invoices) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Billing</h1>
          <p className="text-sm text-gray-500 mt-1">Create and track patient invoices.</p>
        </div>
        <Button onClick={() => setShowForm((s) => !s)}>{showForm ? 'Close' : '+ New Invoice'}</Button>
      </div>

      {showForm && (
        <Card className="p-5">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <Input label="Patient name" required value={form.patientName} onChange={(e) => setForm((f) => ({ ...f, patientName: e.target.value }))} />
              <Input label="Patient phone" value={form.patientPhone} onChange={(e) => setForm((f) => ({ ...f, patientPhone: e.target.value }))} />
              <Input label="Due date" type="date" value={form.dueDate} onChange={(e) => setForm((f) => ({ ...f, dueDate: e.target.value }))} />
            </div>

            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Line items</p>
              <div className="space-y-2">
                {items.map((it, i) => (
                  <div key={i} className="grid grid-cols-[1fr,100px,120px] gap-2">
                    <Input placeholder="Description" value={it.description} onChange={(e) => updateItem(i, 'description', e.target.value)} />
                    <Input type="number" placeholder="Qty" value={it.quantity} onChange={(e) => updateItem(i, 'quantity', e.target.value)} />
                    <Input type="number" placeholder="Unit price ₹" value={it.unitPrice} onChange={(e) => updateItem(i, 'unitPrice', e.target.value)} />
                  </div>
                ))}
              </div>
              <div className="flex items-center justify-between mt-2">
                <Button type="button" size="sm" variant="secondary" onClick={() => setItems((its) => [...its, { ...emptyItem }])}>+ Add line</Button>
                <p className="text-sm text-gray-500">Subtotal: <span className="font-semibold text-gray-900">{formatCurrency(total)}</span></p>
              </div>
            </div>

            {formError && <p className="text-sm text-rose-600">{formError}</p>}
            <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Create Invoice'}</Button>
          </form>
        </Card>
      )}

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <Card>
        <Table
          rows={invoices}
          emptyMessage="No invoices yet."
          columns={[
            { key: 'invoice_number', header: 'Invoice' },
            { key: 'patient_name', header: 'Patient' },
            { key: 'total', header: 'Total', render: (r) => formatCurrency(r.total) },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'due_date', header: 'Due', render: (r) => formatDate(r.due_date) },
            { key: 'actions', header: '', render: (r) => r.status !== 'paid' && (
              <Button size="sm" disabled={busyId === r.id} onClick={() => markPaid(r.id)}>Mark Paid</Button>
            ) },
          ]}
        />
      </Card>
    </div>
  );
}
