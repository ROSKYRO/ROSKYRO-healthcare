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

  const load = useCallback(() => {
    api.get('/billing').then((res) => setInvoices(res.data.invoices)).catch((err) => { if (err?.response?.status === 402) setBlocked(true); });
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
    await api.post('/billing', { ...form, lineItems });
    setShowForm(false);
    setForm({ patientName: '', patientPhone: '', dueDate: '' });
    setItems([{ ...emptyItem }]);
    load();
  }

  async function markPaid(id) {
    setBusyId(id);
    try {
      await api.patch(`/billing/${id}`, { status: 'paid' });
      load();
    } finally {
      setBusyId(null);
    }
  }

  if (blocked) return <UpgradePrompt pillar="manage" />;
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

            <Button type="submit">Create Invoice</Button>
          </form>
        </Card>
      )}

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
