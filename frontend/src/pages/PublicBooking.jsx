import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import api from '../lib/api';
import { Card, Button, Input, Textarea, Spinner, formatCurrency } from '../components/ui';

function fmtDateLabel(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  const label = d.toLocaleDateString('en-IN', { weekday: 'short', day: '2-digit', month: 'short' });
  return isToday ? `Today, ${label}` : label;
}

export default function PublicBooking() {
  const { orgId } = useParams();
  // loading | notfound | closed | pick-doctor | ready | payment | success | error
  const [state, setState] = useState('loading');
  const [page, setPage] = useState(null); // org + doctor roster
  const [selectedDoctor, setSelectedDoctor] = useState(null);
  const [availability, setAvailability] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [selectedDate, setSelectedDate] = useState(null);
  const [selectedTime, setSelectedTime] = useState(null);
  const [form, setForm] = useState({ patientName: '', patientPhone: '', note: '' });
  const [result, setResult] = useState(null);
  const [confirming, setConfirming] = useState(false); // true only while the actual booking API call is in flight

  function loadPage() {
    setState('loading');
    api.get(`/public/booking/${orgId}`)
      .then((res) => {
        setPage(res.data);
        setState('pick-doctor');
      })
      .catch((err) => {
        const status = err?.response?.status;
        if (status === 404) {
          setErrorMsg(err.response.data?.error || 'This booking link is not available.');
          setState('closed');
        } else {
          setErrorMsg('Could not load booking page. Please try again.');
          setState('error');
        }
      });
  }

  useEffect(loadPage, [orgId]);

  function chooseDoctor(doctor) {
    setSelectedDoctor(doctor);
    setSelectedDate(null);
    setSelectedTime(null);
    setState('loading');
    api.get(`/public/booking/${orgId}/doctors/${doctor.id}/availability`)
      .then((res) => {
        setAvailability(res.data);
        setSelectedDate(res.data.days[0]?.date || null);
        setState('ready');
      })
      .catch(() => {
        setErrorMsg('Could not load this doctor’s availability. Please try again.');
        setState('error');
      });
  }

  function backToDoctors() {
    setSelectedDoctor(null);
    setAvailability(null);
    setSelectedDate(null);
    setSelectedTime(null);
    setState('pick-doctor');
  }

  // Booking is only ever created — and a token only ever issued — once
  // payment is done. A doctor with a consultation fee sends the patient to
  // a payment step first (pay via the clinic's UPI, then confirm); the
  // actual booking API call only fires from that confirm click. Free
  // doctors (fee 0) skip the payment step and book straight through. There
  // is no "payment pending" state for QR bookings by design.
  function reviewDetails(e) {
    e.preventDefault();
    if (!selectedDate || !selectedTime || !selectedDoctor) return;
    const fee = Number(selectedDoctor.consultationFee) || 0;
    setErrorMsg('');
    if (fee > 0) {
      setState('payment');
    } else {
      doBook();
    }
  }

  async function doBook() {
    setConfirming(true);
    setErrorMsg('');
    try {
      const { data: res } = await api.post(`/public/booking/${orgId}/book`, {
        patientName: form.patientName,
        patientPhone: form.patientPhone,
        doctorId: selectedDoctor.id,
        appointmentDate: selectedDate,
        appointmentTime: selectedTime,
        note: form.note,
      });
      setResult(res);
      setState('success');
    } catch (err) {
      setErrorMsg(err?.response?.data?.error || 'Could not complete booking. Please try again.');
      if (err?.response?.status === 409) {
        setState('ready');
        chooseDoctor(selectedDoctor); // slot filled — refresh availability
      }
      // otherwise stay on whichever screen (ready/payment) so they can retry
    } finally {
      setConfirming(false);
    }
  }

  if (state === 'loading') {
    return <CenterShell><Spinner className="h-8 w-8" /></CenterShell>;
  }

  if (state === 'closed' || state === 'error') {
    return (
      <CenterShell>
        <Card className="p-8 text-center max-w-sm">
          <div className="h-10 w-10 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center text-xl mx-auto">!</div>
          <p className="text-sm font-medium text-gray-800 mt-4">{errorMsg}</p>
        </Card>
      </CenterShell>
    );
  }

  if (state === 'success' && result) {
    return (
      <CenterShell>
        <Card className="p-8 max-w-sm w-full text-center">
          <div className="h-12 w-12 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center text-2xl mx-auto">✓</div>
          <h2 className="text-lg font-bold text-gray-900 mt-4">Booking Confirmed</h2>
          <p className="text-sm text-gray-500 mt-1">
            {result.doctor?.name}{result.doctor?.specialty ? ` (${result.doctor.specialty})` : ''} — your token number is
          </p>
          <p className="text-4xl font-extrabold text-brand-700 mt-2">#{result.tokenNumber}</p>
          <p className="text-xs text-gray-400 mt-2">
            {fmtDateLabel(selectedDate)} · {selectedTime}
          </p>

          {result.payment?.collected ? (
            <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-left">
              <p className="text-sm font-semibold text-emerald-800">Payment received — {formatCurrency(result.payment.amount)}</p>
              <p className="text-xs text-emerald-700 mt-1">Paid via UPI to: <span className="font-mono font-bold text-gray-900">{result.payment.upiId}</span></p>
              <p className="text-xs text-emerald-700 mt-2">
                Reception par apna naam aur token number (#{result.tokenNumber}) bata dein.
              </p>
            </div>
          ) : (
            <p className="text-xs text-gray-500 mt-4">No payment required — reception par apna token number bata dein.</p>
          )}
        </Card>
      </CenterShell>
    );
  }

  if (state === 'pick-doctor') {
    return (
      <CenterShell wide>
        <Card className="p-6 sm:p-8 max-w-lg w-full">
          <div className="text-center mb-5">
            <p className="text-xs font-semibold text-brand-600 tracking-wide">ROSKYRO ONLINE BOOKING</p>
            <h1 className="text-xl font-bold text-gray-900 mt-1">{page.org.name}</h1>
            <p className="text-sm text-gray-500 mt-1">Kis doctor / faculty ke paas appointment chahiye?</p>
          </div>

          {page.doctors.length === 0 ? (
            <p className="text-sm text-gray-400 text-center py-8">Abhi koi doctor booking ke liye available nahi hai.</p>
          ) : (
            <div className="space-y-2">
              {page.doctors.map((d) => (
                <button
                  type="button"
                  key={d.id}
                  onClick={() => chooseDoctor(d)}
                  className="w-full flex items-center justify-between gap-3 rounded-xl border border-gray-200 hover:border-brand-400 hover:bg-brand-50 transition px-4 py-3 text-left"
                >
                  <div>
                    <p className="font-semibold text-gray-900">{d.name}</p>
                    {d.specialty && <p className="text-xs text-gray-500">{d.specialty}</p>}
                  </div>
                  <span className="text-sm font-medium text-brand-700 shrink-0">
                    {d.consultationFee > 0 ? formatCurrency(d.consultationFee) : 'Free'}
                  </span>
                </button>
              ))}
            </div>
          )}
        </Card>
      </CenterShell>
    );
  }

  if (state === 'payment' && selectedDoctor) {
    const fee = Number(selectedDoctor.consultationFee) || 0;
    return (
      <CenterShell>
        <Card className="p-8 max-w-sm w-full text-center">
          <p className="text-xs font-semibold text-brand-600 tracking-wide">STEP 2 OF 2 — PAYMENT</p>
          <h2 className="text-lg font-bold text-gray-900 mt-2">Pay to confirm your booking</h2>
          <p className="text-sm text-gray-500 mt-1">
            {selectedDoctor.name}{selectedDoctor.specialty ? ` — ${selectedDoctor.specialty}` : ''}
          </p>
          <p className="text-3xl font-extrabold text-brand-700 mt-3">{formatCurrency(fee)}</p>
          <p className="text-xs text-gray-400 mt-1">{fmtDateLabel(selectedDate)} · {selectedTime}</p>

          <div className="mt-5 rounded-xl border border-gray-200 bg-gray-50 p-4 text-left">
            <p className="text-xs text-gray-500">Pay via UPI to:</p>
            <p className="text-base font-mono font-bold text-gray-900 mt-1 break-all">{page?.settings?.upiId}</p>
            <p className="text-xs text-gray-500 mt-3">
              Booking sirf tabhi confirm hogi aur token sirf tabhi milega jab payment ho chuki ho — pehle UPI se pay karein, phir neeche confirm karein.
            </p>
          </div>

          {errorMsg && <p className="text-sm text-rose-600 mt-3">{errorMsg}</p>}

          <div className="mt-5 space-y-2">
            <Button className="w-full" onClick={doBook} disabled={confirming}>
              {confirming ? 'Confirming…' : 'Maine Payment Kar Diya — Confirm Booking'}
            </Button>
            <button type="button" onClick={() => setState('ready')} className="text-xs font-medium text-gray-500 hover:text-gray-700">
              &larr; Back to booking details
            </button>
          </div>
        </Card>
      </CenterShell>
    );
  }

  const day = availability?.days?.find((d) => d.date === selectedDate);

  return (
    <CenterShell wide>
      <Card className="p-6 sm:p-8 max-w-lg w-full">
        <div className="mb-5">
          <button type="button" onClick={backToDoctors} className="text-xs font-medium text-gray-500 hover:text-gray-700">&larr; Change doctor</button>
          <div className="text-center mt-2">
            <p className="text-xs font-semibold text-brand-600 tracking-wide">ROSKYRO ONLINE BOOKING</p>
            <h1 className="text-xl font-bold text-gray-900 mt-1">{page.org.name}</h1>
            <p className="text-sm text-gray-700 font-medium">{selectedDoctor.name}</p>
            {selectedDoctor.specialty && <p className="text-xs text-gray-500">{selectedDoctor.specialty}</p>}
            <p className="text-sm text-gray-500 mt-1">
              {Number(availability.doctor.consultationFee) > 0 ? `Consultation fee: ${formatCurrency(availability.doctor.consultationFee)}` : 'No consultation fee'}
            </p>
          </div>
        </div>

        <form onSubmit={reviewDetails} className="space-y-5">
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Choose a date</p>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {availability.days.map((d) => (
                <button
                  type="button"
                  key={d.date}
                  onClick={() => { setSelectedDate(d.date); setSelectedTime(null); }}
                  disabled={d.slots.length === 0}
                  className={`shrink-0 px-3 py-2 rounded-lg text-xs font-medium border
                    ${d.slots.length === 0 ? 'bg-gray-50 text-gray-300 border-gray-100 cursor-not-allowed'
                      : selectedDate === d.date ? 'bg-brand-600 text-white border-brand-600' : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}
                >
                  {fmtDateLabel(d.date)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Choose a time slot</p>
            <div className="grid grid-cols-3 gap-2">
              {day?.slots.map((s) => (
                <button
                  type="button"
                  key={s.time}
                  disabled={s.remaining <= 0}
                  onClick={() => setSelectedTime(s.time)}
                  className={`px-2 py-2 rounded-lg text-xs font-medium border transition
                    ${s.remaining <= 0 ? 'bg-gray-50 text-gray-300 border-gray-100 cursor-not-allowed line-through'
                      : selectedTime === s.time ? 'bg-brand-600 text-white border-brand-600'
                      : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}`}
                >
                  {s.time}
                </button>
              ))}
              {day && day.slots.length === 0 && <p className="text-xs text-gray-400 col-span-3">Is doctor ke paas is din slot nahi hai — koi aur date try karein.</p>}
            </div>
          </div>

          <Input
            label="Your full name"
            required
            value={form.patientName}
            onChange={(e) => setForm((f) => ({ ...f, patientName: e.target.value }))}
          />
          <Input
            label="Your phone number"
            required
            type="tel"
            value={form.patientPhone}
            onChange={(e) => setForm((f) => ({ ...f, patientPhone: e.target.value }))}
          />
          <Textarea
            label="Reason for visit (optional)"
            rows={2}
            value={form.note}
            onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
          />

          {errorMsg && <p className="text-sm text-rose-600">{errorMsg}</p>}

          <Button type="submit" className="w-full" disabled={!selectedDate || !selectedTime || confirming}>
            {confirming ? 'Booking…' : Number(selectedDoctor.consultationFee) > 0 ? 'Continue to Payment' : 'Confirm Booking'}
          </Button>
        </form>
      </Card>
    </CenterShell>
  );
}

function CenterShell({ children, wide }) {
  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4 py-8">
      <div className={`w-full ${wide ? 'max-w-lg' : 'max-w-sm'} flex flex-col items-center`}>{children}</div>
    </div>
  );
}
