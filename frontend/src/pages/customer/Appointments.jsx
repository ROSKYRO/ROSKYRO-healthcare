import { useEffect, useState } from 'react';
import api from '../../lib/api';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, Table, Badge, Button, Input, PageLoading, formatDate, formatCurrency } from '../../components/ui';

export default function Appointments() {
  const [appointments, setAppointments] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ patientName: '', doctorName: '', appointmentDate: '', appointmentTime: '', revenueAmount: '', isNewPatient: false });
  const [pdfDate, setPdfDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState('');
  const [error, setError] = useState('');
  const [formError, setFormError] = useState('');
  const [saving, setSaving] = useState(false);

  function load() {
    setError('');
    api.get('/appointments').then((res) => setAppointments(res.data.appointments)).catch((err) => {
      if (err?.response?.status === 402) setBlocked(true);
      else setError('Could not load appointments. Please try again.');
    });
  }

  useEffect(load, []);

  async function handleSubmit(e) {
    e.preventDefault();
    setFormError('');
    setSaving(true);
    try {
      await api.post('/appointments', { ...form, revenueAmount: form.revenueAmount ? Number(form.revenueAmount) : 0 });
      setShowForm(false);
      setForm({ patientName: '', doctorName: '', appointmentDate: '', appointmentTime: '', revenueAmount: '', isNewPatient: false });
      load();
    } catch (err) {
      setFormError(err?.response?.data?.error || 'Could not save this appointment. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  async function downloadDailyPdf() {
    setPdfBusy(true);
    setPdfError('');
    try {
      const res = await api.get('/appointments/daily-pdf', { params: { date: pdfDate }, responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: 'application/pdf' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `paid-appointments-${pdfDate}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setPdfError('Could not generate the PDF. Please try again.');
    } finally {
      setPdfBusy(false);
    }
  }

  if (blocked) return <UpgradePrompt pillar="manage" />;

  if (error && !appointments) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{error}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
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

      <Card className="p-5">
        <div className="flex flex-wrap items-end gap-3">
          <Input label="Date" type="date" value={pdfDate} onChange={(e) => setPdfDate(e.target.value)} className="max-w-xs" />
          <Button variant="secondary" onClick={downloadDailyPdf} disabled={pdfBusy}>
            {pdfBusy ? 'Generating…' : '⬇ Download Paid Appointments PDF'}
          </Button>
        </div>
        <p className="text-xs text-gray-400 mt-2">Downloads a PDF of that day's paid appointment bookings.</p>
        {pdfError && <p className="text-sm text-rose-600 mt-2">{pdfError}</p>}
      </Card>

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
            {formError && <p className="text-sm text-rose-600 col-span-2">{formError}</p>}
            <div className="col-span-2"><Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save Appointment'}</Button></div>
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
