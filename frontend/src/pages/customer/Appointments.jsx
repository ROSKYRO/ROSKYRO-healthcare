import { useEffect, useState } from 'react';
import api from '../../lib/api';
import { Card, Table, Badge, Button, Input, PageLoading, formatDate, formatCurrency } from '../../components/ui';

export default function Appointments() {
  const [appointments, setAppointments] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ patientName: '', doctorName: '', appointmentDate: '', appointmentTime: '', revenueAmount: '', isNewPatient: false });

  function load() {
    api.get('/appointments').then((res) => setAppointments(res.data.appointments));
  }

  useEffect(load, []);

  async function handleSubmit(e) {
    e.preventDefault();
    await api.post('/appointments', { ...form, revenueAmount: form.revenueAmount ? Number(form.revenueAmount) : 0 });
    setShowForm(false);
    setForm({ patientName: '', doctorName: '', appointmentDate: '', appointmentTime: '', revenueAmount: '', isNewPatient: false });
    load();
  }

  if (!appointments) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Appointments</h1>
          <p className="text-sm text-gray-500 mt-1">Your patient schedule and visit history.</p>
        </div>
        <Button onClick={() => setShowForm((s) => !s)}>{showForm ? 'Close' : '+ New Appointment'}</Button>
      </div>

      {showForm && (
        <Card className="p-5">
          <form onSubmit={handleSubmit} className="grid grid-cols-2 gap-4">
            <Input label="Patient name" required value={form.patientName} onChange={(e) => setForm((f) => ({ ...f, patientName: e.target.value }))} />
            <Input label="Doctor" value={form.doctorName} onChange={(e) => setForm((f) => ({ ...f, doctorName: e.target.value }))} />
            <Input label="Date" type="date" required value={form.appointmentDate} onChange={(e) => setForm((f) => ({ ...f, appointmentDate: e.target.value }))} />
            <Input label="Time" type="time" value={form.appointmentTime} onChange={(e) => setForm((f) => ({ ...f, appointmentTime: e.target.value }))} />
            <Input label="Expected revenue (₹)" type="number" value={form.revenueAmount} onChange={(e) => setForm((f) => ({ ...f, revenueAmount: e.target.value }))} />
            <label className="flex items-center gap-2 text-sm mt-6">
              <input type="checkbox" checked={form.isNewPatient} onChange={(e) => setForm((f) => ({ ...f, isNewPatient: e.target.checked }))} />
              New patient
            </label>
            <div className="col-span-2"><Button type="submit">Save Appointment</Button></div>
          </form>
        </Card>
      )}

      <Card>
        <Table
          rows={appointments}
          columns={[
            { key: 'appointment_date', header: 'Date', render: (r) => formatDate(r.appointment_date) },
            { key: 'appointment_time', header: 'Time', render: (r) => r.appointment_time?.slice(0, 5) || '—' },
            { key: 'patient_name', header: 'Patient' },
            { key: 'doctor_name', header: 'Doctor' },
            { key: 'source', header: 'Source', render: (r) => <Badge tone="slate">{r.source}</Badge> },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            { key: 'revenue_amount', header: 'Revenue', render: (r) => formatCurrency(r.revenue_amount) },
          ]}
        />
      </Card>
    </div>
  );
}
