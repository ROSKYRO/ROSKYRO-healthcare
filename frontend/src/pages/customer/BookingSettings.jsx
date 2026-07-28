import { useEffect, useState, useCallback, useRef } from 'react';
import QRCode from 'qrcode';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import UpgradePrompt from '../../components/UpgradePrompt';
import { Card, CardHeader, Table, Badge, Button, Input, PageLoading, formatDateTime, formatCurrency } from '../../components/ui';

const DAYS = [
  { key: 'mon', label: 'Mon' },
  { key: 'tue', label: 'Tue' },
  { key: 'wed', label: 'Wed' },
  { key: 'thu', label: 'Thu' },
  { key: 'fri', label: 'Fri' },
  { key: 'sat', label: 'Sat' },
  { key: 'sun', label: 'Sun' },
];

function Toggle({ checked, onChange, label }) {
  return (
    <label className="flex items-center gap-3 cursor-pointer select-none">
      <span className="relative inline-block w-11 h-6">
        <input type="checkbox" className="sr-only peer" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span className="absolute inset-0 rounded-full bg-gray-300 peer-checked:bg-brand-600 transition" />
        <span className="absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition peer-checked:translate-x-5" />
      </span>
      <span className="text-sm font-medium text-gray-700">{label}</span>
    </label>
  );
}

function QrPanel({ orgId, enabled }) {
  const [dataUrl, setDataUrl] = useState(null);
  const linkRef = useRef(null);
  const bookingUrl = `${window.location.origin}/book/${orgId}`;

  useEffect(() => {
    QRCode.toDataURL(bookingUrl, { width: 260, margin: 1, color: { dark: '#0b1f3a', light: '#ffffff' } }).then(setDataUrl);
  }, [bookingUrl]);

  function copyLink() {
    navigator.clipboard?.writeText(bookingUrl);
    if (linkRef.current) {
      linkRef.current.select();
    }
  }

  function download() {
    if (!dataUrl) return;
    const a = document.createElement('a');
    a.href = dataUrl;
    a.download = 'roskyro-booking-qr.png';
    a.click();
  }

  return (
    <Card>
      <CardHeader
        title="Your Booking QR Code"
        subtitle="Print this at the front desk. One QR code for the whole clinic — the patient picks which doctor/faculty they want after scanning, pays via your UPI ID, and gets a token number for that doctor's own queue."
      />
      <div className="px-5 pb-5 flex flex-col sm:flex-row items-center gap-6">
        <div className={`p-3 rounded-xl border ${enabled ? 'border-gray-200' : 'border-dashed border-gray-300 opacity-40'}`}>
          {dataUrl ? <img src={dataUrl} alt="Booking QR code" width={200} height={200} /> : <div className="w-[200px] h-[200px] bg-gray-100 animate-pulse rounded" />}
        </div>
        <div className="flex-1 w-full space-y-3">
          {!enabled && (
            <p className="text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              Online booking abhi band hai — neeche "Enable online QR booking" on karo taaki ye link patients ke liye kaam kare.
            </p>
          )}
          <Input label="Booking link" readOnly value={bookingUrl} ref={linkRef} onFocus={(e) => e.target.select()} />
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" onClick={copyLink}>Copy Link</Button>
            <Button size="sm" variant="secondary" onClick={download} disabled={!dataUrl}>Download QR (PNG)</Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

function emptySchedule() {
  return DAYS.reduce((acc, d) => ({ ...acc, [d.key]: { active: false, openTime: '10:00', closeTime: '13:00' } }), {});
}

function scheduleToForm(weeklySchedule) {
  const base = emptySchedule();
  for (const entry of weeklySchedule || []) {
    base[entry.day] = { active: true, openTime: String(entry.open_time).slice(0, 5), closeTime: String(entry.close_time).slice(0, 5) };
  }
  return base;
}

function scheduleToPayload(scheduleForm) {
  return DAYS.filter((d) => scheduleForm[d.key].active).map((d) => ({
    day: d.key, openTime: scheduleForm[d.key].openTime, closeTime: scheduleForm[d.key].closeTime,
  }));
}

function DoctorForm({ initial, onCancel, onSaved }) {
  const isEdit = !!initial;
  const [form, setForm] = useState({
    name: initial?.name || '',
    specialty: initial?.specialty || '',
    consultationFee: initial?.consultation_fee ?? 0,
    slotDurationMinutes: initial?.slot_duration_minutes ?? 30,
    capacityPerSlot: initial?.capacity_per_slot ?? 1,
  });
  const [schedule, setSchedule] = useState(scheduleToForm(initial?.weekly_schedule));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function setDay(key, patch) {
    setSchedule((s) => ({ ...s, [key]: { ...s[key], ...patch } }));
  }

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    const weeklySchedule = scheduleToPayload(schedule);
    if (!weeklySchedule.length) {
      setError('Kam se kam ek din select karo jab ye doctor available hai.');
      setSaving(false);
      return;
    }
    try {
      const payload = { ...form, weeklySchedule };
      if (isEdit) {
        await api.patch(`/doctors/${initial.id}`, payload);
      } else {
        await api.post('/doctors', payload);
      }
      onSaved();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not save doctor.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4 bg-gray-50 rounded-xl border border-gray-200 p-4">
      <div className="grid sm:grid-cols-2 gap-3">
        <Input label="Doctor / faculty name" required value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
        <Input label="Specialty (optional)" placeholder="e.g. Pediatrician" value={form.specialty} onChange={(e) => setForm((f) => ({ ...f, specialty: e.target.value }))} />
        <Input label="Consultation fee (₹, 0 = free)" type="number" min="0" step="1" value={form.consultationFee} onChange={(e) => setForm((f) => ({ ...f, consultationFee: e.target.value }))} />
        <Input label="Slot length (minutes)" type="number" min="5" step="5" value={form.slotDurationMinutes} onChange={(e) => setForm((f) => ({ ...f, slotDurationMinutes: e.target.value }))} />
        <Input label="Patients allowed per slot" type="number" min="1" step="1" value={form.capacityPerSlot} onChange={(e) => setForm((f) => ({ ...f, capacityPerSlot: e.target.value }))} />
      </div>

      <div>
        <p className="text-sm font-medium text-gray-700 mb-2">Weekly schedule — is doctor ke available din aur time</p>
        <div className="space-y-2">
          {DAYS.map((d) => (
            <div key={d.key} className="flex items-center gap-3 text-sm">
              <label className="flex items-center gap-2 w-16 shrink-0">
                <input type="checkbox" checked={schedule[d.key].active} onChange={(e) => setDay(d.key, { active: e.target.checked })} />
                <span className="font-medium text-gray-700">{d.label}</span>
              </label>
              <input
                type="time" disabled={!schedule[d.key].active}
                value={schedule[d.key].openTime}
                onChange={(e) => setDay(d.key, { openTime: e.target.value })}
                className="rounded-lg border border-gray-300 px-2 py-1 text-xs disabled:bg-gray-100 disabled:text-gray-400"
              />
              <span className="text-gray-400">to</span>
              <input
                type="time" disabled={!schedule[d.key].active}
                value={schedule[d.key].closeTime}
                onChange={(e) => setDay(d.key, { closeTime: e.target.value })}
                className="rounded-lg border border-gray-300 px-2 py-1 text-xs disabled:bg-gray-100 disabled:text-gray-400"
              />
            </div>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}
      <div className="flex items-center gap-3">
        <Button type="submit" size="sm" disabled={saving}>{saving ? 'Saving…' : isEdit ? 'Save Changes' : 'Add Doctor'}</Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}

function DoctorRow({ doctor, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const activeDays = (doctor.weekly_schedule || []).map((e) => DAYS.find((d) => d.key === e.day)?.label || e.day);

  async function toggleActive() {
    setBusy(true);
    setError('');
    try {
      if (doctor.is_active) {
        await api.delete(`/doctors/${doctor.id}`);
      } else {
        await api.patch(`/doctors/${doctor.id}`, { isActive: true });
      }
      onChanged();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not update this doctor. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return <DoctorForm initial={doctor} onCancel={() => setEditing(false)} onSaved={() => { setEditing(false); onChanged(); }} />;
  }

  return (
    <div className={`flex items-start justify-between gap-4 rounded-xl border p-4 ${doctor.is_active ? 'border-gray-200' : 'border-gray-100 bg-gray-50 opacity-60'}`}>
      <div>
        <div className="flex items-center gap-2">
          <p className="font-semibold text-gray-900">{doctor.name}</p>
          {!doctor.is_active && <Badge tone="slate">Inactive</Badge>}
        </div>
        {doctor.specialty && <p className="text-sm text-gray-500">{doctor.specialty}</p>}
        <p className="text-xs text-gray-400 mt-1">
          {formatCurrency(doctor.consultation_fee)} · {doctor.slot_duration_minutes} min slots · {doctor.capacity_per_slot} patient(s)/slot
        </p>
        <p className="text-xs text-gray-400 mt-1">
          {activeDays.length ? `Available: ${activeDays.join(', ')}` : 'No days set'}
        </p>
        {error && <p className="text-xs text-rose-600 mt-1">{error}</p>}
      </div>
      <div className="flex flex-col gap-2 shrink-0">
        <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>Edit</Button>
        <Button size="sm" variant={doctor.is_active ? 'danger' : 'secondary'} disabled={busy} onClick={toggleActive}>
          {doctor.is_active ? 'Deactivate' : 'Reactivate'}
        </Button>
      </div>
    </div>
  );
}

function DoctorsPanel() {
  const [doctorList, setDoctorList] = useState(null);
  const [adding, setAdding] = useState(false);
  const [loadError, setLoadError] = useState('');

  const load = useCallback(() => {
    setLoadError('');
    api.get('/doctors').then((res) => setDoctorList(res.data.doctors)).catch(() => {
      setLoadError('Could not load doctors. Please try again.');
    });
  }, []);

  useEffect(load, [load]);

  return (
    <Card>
      <CardHeader
        title="Doctors & Faculty"
        subtitle="Multispeciality clinic/hospital me har doctor ka apna din/time aur fee hota hai — yahan se manage karo. Patient QR scan karne ke baad yahi list se apna doctor choose karega."
        action={!adding && <Button size="sm" onClick={() => setAdding(true)}>+ Add Doctor</Button>}
      />
      <div className="px-5 pb-5 space-y-3">
        {adding && (
          <DoctorForm onCancel={() => setAdding(false)} onSaved={() => { setAdding(false); load(); }} />
        )}
        {loadError ? (
          <div className="text-center py-6">
            <p className="text-sm text-rose-600">{loadError}</p>
            <Button size="sm" variant="secondary" className="mt-3" onClick={load}>Retry</Button>
          </div>
        ) : doctorList === null ? (
          <PageLoading />
        ) : doctorList.length === 0 && !adding ? (
          <p className="text-sm text-gray-400 py-6 text-center">Abhi tak koi doctor add nahi hua. Patients tab tak booking nahi kar payenge.</p>
        ) : (
          doctorList.map((d) => <DoctorRow key={d.id} doctor={d} onChanged={load} />)
        )}
      </div>
    </Card>
  );
}

export default function BookingSettings() {
  const { user } = useAuth();
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState(null);
  const [bookings, setBookings] = useState([]);
  const [blocked, setBlocked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [loadError, setLoadError] = useState('');

  const load = useCallback(() => {
    setLoadError('');
    Promise.all([api.get('/booking-settings'), api.get('/appointments')])
      .then(([s, a]) => {
        setSettings(s.data.settings);
        setForm({
          isEnabled: s.data.settings.is_enabled,
          upiId: s.data.settings.upi_id || '',
          bookingWindowDays: s.data.settings.booking_window_days,
        });
        setBookings(a.data.appointments.filter((ap) => ap.booked_via === 'qr_booking'));
      })
      .catch((err) => {
        if (err?.response?.status === 402) setBlocked(true);
        else setLoadError('Could not load booking settings. Please try again.');
      });
  }, []);

  useEffect(load, [load]);

  async function save(e) {
    e.preventDefault();
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const { data } = await api.patch('/booking-settings', form);
      setSettings(data.settings);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not save settings.');
    } finally {
      setSaving(false);
    }
  }

  async function markPaid(id) {
    setBusyId(id);
    setError(null);
    try {
      await api.patch(`/appointments/${id}`, { paymentStatus: 'paid' });
      load();
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not mark this booking as paid. Please try again.');
    } finally {
      setBusyId(null);
    }
  }

  if (blocked) return <UpgradePrompt pillar="manage" />;
  if (loadError) {
    return (
      <div className="text-center py-16">
        <p className="text-sm text-rose-600">{loadError}</p>
        <Button size="sm" variant="secondary" className="mt-4" onClick={load}>Retry</Button>
      </div>
    );
  }
  if (!settings || !form) return <PageLoading />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Online Booking (QR)</h1>
        <p className="text-sm text-gray-500 mt-1">
          Patient QR se scan karke pehle doctor/faculty choose karta hai, phir uske slot me khud apna appointment book karta hai, UPI par payment karta hai, aur us doctor ki apni line mein token number ke hisaab se book ho jaata hai.
        </p>
      </div>

      <QrPanel orgId={user.orgId} enabled={settings.is_enabled} />

      <Card>
        <CardHeader title="Booking Settings" subtitle="Poori clinic ke liye QR link on/off aur UPI ID — har doctor ka apna time/fee neeche Doctors & Faculty section me set hota hai." />
        <form onSubmit={save} className="px-5 pb-5 space-y-5">
          <Toggle checked={form.isEnabled} onChange={(v) => setForm((f) => ({ ...f, isEnabled: v }))} label="Enable online QR booking" />

          <div className="grid sm:grid-cols-2 gap-4">
            <Input
              label="Your UPI ID (patient payment)"
              placeholder="clinic@okhdfcbank"
              value={form.upiId}
              onChange={(e) => setForm((f) => ({ ...f, upiId: e.target.value }))}
            />
            <Input
              label="How many days ahead patients can book"
              type="number" min="1" max="60" step="1"
              value={form.bookingWindowDays}
              onChange={(e) => setForm((f) => ({ ...f, bookingWindowDays: e.target.value }))}
            />
          </div>

          {error && <p className="text-sm text-rose-600">{error}</p>}
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save Settings'}</Button>
            {saved && <span className="text-sm text-emerald-600 font-medium">Saved ✓</span>}
          </div>
        </form>
      </Card>

      <DoctorsPanel />

      <Card>
        <CardHeader title="QR Bookings" subtitle="Patients jo QR scan karke aaye — kis doctor ke paas, token number, payment status, sab yahan dikhega." />
        <Table
          rows={bookings}
          emptyMessage="Abhi tak koi QR booking nahi aayi."
          columns={[
            { key: 'token_number', header: 'Token', render: (r) => <span className="font-bold text-brand-700">#{r.token_number}</span> },
            { key: 'doctor_name', header: 'Doctor', render: (r) => r.doctor_name || '—' },
            { key: 'patient_name', header: 'Patient' },
            { key: 'patient_phone', header: 'Phone' },
            { key: 'appointment_date', header: 'Date', render: (r) => formatDateTime(r.appointment_date).split(',')[0] },
            { key: 'appointment_time', header: 'Time', render: (r) => String(r.appointment_time).slice(0, 5) },
            { key: 'payment_status', header: 'Payment', render: (r) => <Badge tone={r.payment_status === 'paid' ? 'paid' : r.payment_status === 'pending' ? 'pending' : 'slate'}>{r.payment_status.replace(/_/g, ' ')}</Badge> },
            { key: 'status', header: 'Status', render: (r) => <Badge tone={r.status}>{r.status}</Badge> },
            {
              key: 'actions', header: '', render: (r) => r.payment_status === 'pending' && (
                <Button size="sm" disabled={busyId === r.id} onClick={() => markPaid(r.id)}>Mark Paid</Button>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
