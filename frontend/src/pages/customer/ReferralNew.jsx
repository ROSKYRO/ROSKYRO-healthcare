import { useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { canCreateReferrals } from '../../lib/referralRights';
import { Card, Button, Input, Select, Textarea, Badge, EmptyState } from '../../components/ui';

// The 3-click referral flow:
//   1. Type/scan the patient's booking code (from QR self-booking) and hit
//      Enter -> their name + phone auto-fill. No booking code on file (a
//      walk-in, or an appointment taken over the counter)? Just type the
//      name/phone in by hand instead -- nothing here is required to proceed.
//   2. Type what the patient needs (e.g. "blood test", "xray", "cardiologist")
//      -> every partner in the network offering that shows up live.
//   3. Click one of them -> the referral fires immediately.
// Urgency + clinical notes are folded in as one small optional toggle
// (default: routine, no notes) rather than a separate full form -- they're
// clinically useful often enough to keep, but shouldn't cost an extra step
// for the common case.
export default function ReferralNew() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [bookingCode, setBookingCode] = useState('');
  const [bookingLookup, setBookingLookup] = useState('idle'); // idle | loading | found | notfound
  const [patientLocked, setPatientLocked] = useState(false);

  const [form, setForm] = useState({
    patientName: '', patientPhone: '', patientAge: '', patientGender: '',
    clinicalNotes: '', urgency: 'routine',
  });
  const [showMoreDetails, setShowMoreDetails] = useState(false);

  const [serviceKeyword, setServiceKeyword] = useState('');
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [searchedOnce, setSearchedOnce] = useState(false);
  const [searchLocked, setSearchLocked] = useState(false);
  const [searchError, setSearchError] = useState('');
  const debounceRef = useRef(null);

  const [referringPartnerId, setReferringPartnerId] = useState(null);
  const [error, setError] = useState('');

  // Debounced live search as the service keyword is typed.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const keyword = serviceKeyword.trim();
    if (!keyword) { setSearchResults([]); setSearchedOnce(false); return; }
    setSearching(true);
    setSearchLocked(false);
    setSearchError('');
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await api.get('/partners/search-by-service', { params: { keyword } });
        setSearchResults(res.data.partners);
      } catch (err) {
        // Previously uncaught: this endpoint 402s when the org's
        // Networking Marketing plan isn't active, and any error silently
        // rendered "no partners found" -- misleading the user into
        // thinking the search just came up empty rather than that the
        // plan needs activating (or the request failed for another
        // reason).
        setSearchResults([]);
        if (err?.response?.status === 402) {
          setSearchLocked(true);
        } else {
          setSearchError(err?.response?.data?.error || 'Could not search partners. Please try again.');
        }
      } finally {
        setSearching(false);
        setSearchedOnce(true);
      }
    }, 350);
    return () => clearTimeout(debounceRef.current);
  }, [serviceKeyword]);

  async function lookupBooking(e) {
    e.preventDefault();
    const code = bookingCode.trim();
    if (!code) return;
    setBookingLookup('loading');
    setError('');
    try {
      const res = await api.get(`/appointments/lookup/${encodeURIComponent(code)}`);
      const appt = res.data.appointment;
      setForm((f) => ({ ...f, patientName: appt.patient_name || '', patientPhone: appt.patient_phone || '' }));
      setPatientLocked(true);
      setBookingLookup('found');
    } catch (err) {
      setBookingLookup('notfound');
      setPatientLocked(false);
    }
  }

  function clearBooking() {
    setBookingCode('');
    setBookingLookup('idle');
    setPatientLocked(false);
    setForm((f) => ({ ...f, patientName: '', patientPhone: '' }));
  }

  function setField(key) {
    return (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  async function referTo(partner) {
    setError('');
    if (!form.patientName.trim()) {
      setError('Patient ka naam zaroori hai — booking code se auto-fill karo ya khud bhar do.');
      return;
    }
    setReferringPartnerId(partner.id);
    try {
      const { data } = await api.post('/referrals', {
        partnerId: partner.id,
        patientName: form.patientName,
        patientPhone: form.patientPhone || undefined,
        patientAge: form.patientAge ? Number(form.patientAge) : undefined,
        patientGender: form.patientGender || undefined,
        serviceRequested: serviceKeyword.trim() || partner.category_name || 'Referral',
        clinicalNotes: form.clinicalNotes || undefined,
        urgency: form.urgency,
      });
      navigate(`/app/referrals/${data.referral.id}`);
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not create referral.');
    } finally {
      setReferringPartnerId(null);
    }
  }

  if (!canCreateReferrals(user)) {
    return (
      <EmptyState
        title="Your business type can't create referrals."
        subtitle="Referral bhejne (partner choose karne) ka right sirf Clinic, Hospital aur Eye Hospital business types ko hai. Aap phir bhi khud ko ek Networking Marketing partner ke roop mein list kar sakte hain, taaki doosre businesses aapko refer kar sakein."
        action={<Link to="/app/become-partner"><Button size="sm">Become a Partner</Button></Link>}
      />
    );
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">New Referral</h1>
        <p className="text-sm text-gray-500 mt-1">Booking code daalo (ya naam/phone khud bharo), jo service chahiye uska keyword type karo, aur ek partner select karo — referral turant ban jaayega.</p>
      </div>

      <Card className="p-6 space-y-5">
        {/* Step 1: booking code -> auto-fill, or manual patient details */}
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">1. Patient</p>
          {!patientLocked ? (
            <form onSubmit={lookupBooking} className="flex gap-2 items-end mb-3">
              <Input
                label="Booking code (optional)"
                placeholder="e.g. BK-000042"
                value={bookingCode}
                onChange={(e) => setBookingCode(e.target.value)}
                className="flex-1"
              />
              <Button type="submit" variant="secondary" disabled={bookingLookup === 'loading' || !bookingCode.trim()}>
                {bookingLookup === 'loading' ? '…' : 'Lookup'}
              </Button>
            </form>
          ) : (
            <div className="flex items-center justify-between rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 mb-3">
              <div>
                <p className="text-sm font-medium text-emerald-800">✓ Auto-filled from booking {bookingCode}</p>
                <p className="text-sm text-emerald-700">{form.patientName} · {form.patientPhone}</p>
              </div>
              <Button type="button" size="sm" variant="ghost" onClick={clearBooking}>Not this patient? Clear</Button>
            </div>
          )}

          {bookingLookup === 'notfound' && (
            <p className="text-xs text-amber-600 mb-3">Booking code nahi mila — patient ki details neeche khud bhar do.</p>
          )}

          {!patientLocked && (
            <div className="grid grid-cols-2 gap-4">
              <Input label="Patient name" required value={form.patientName} onChange={setField('patientName')} />
              <Input label="Patient phone" value={form.patientPhone} onChange={setField('patientPhone')} />
              <Input label="Patient age (optional)" type="number" value={form.patientAge} onChange={setField('patientAge')} />
              <Select label="Gender (optional)" value={form.patientGender} onChange={setField('patientGender')}>
                <option value="">—</option>
                <option>Male</option>
                <option>Female</option>
                <option>Other</option>
              </Select>
            </div>
          )}
        </div>

        {/* Optional: urgency + clinical notes -- collapsed by default */}
        <div>
          <button type="button" className="text-xs text-gray-400 hover:text-gray-600 underline" onClick={() => setShowMoreDetails((s) => !s)}>
            {showMoreDetails ? 'Hide clinical notes / urgency' : `+ Add clinical notes or mark urgent/emergency${form.urgency !== 'routine' ? ` (currently: ${form.urgency})` : ''}`}
          </button>
          {showMoreDetails && (
            <div className="grid grid-cols-2 gap-4 mt-3">
              <Select label="Urgency" value={form.urgency} onChange={setField('urgency')}>
                <option value="routine">Routine</option>
                <option value="urgent">Urgent</option>
                <option value="emergency">Emergency</option>
              </Select>
              <Textarea label="Clinical notes (optional)" rows={2} value={form.clinicalNotes} onChange={setField('clinicalNotes')} className="col-span-2" />
            </div>
          )}
        </div>

        {/* Step 2 + 3: service keyword -> partner list -> click to refer */}
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">2. Service needed → 3. Select a partner</p>
          <Input
            placeholder="e.g. blood test, xray, cardiologist"
            value={serviceKeyword}
            onChange={(e) => setServiceKeyword(e.target.value)}
          />

          {searching && <p className="text-xs text-gray-400 mt-2">Searching…</p>}

          {!searching && searchLocked && (
            <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3">
              <p className="text-sm font-medium text-amber-800">Networking Marketing plan required to search partners.</p>
              <Link to="/app/plans" className="text-sm text-brand-700 font-medium underline">Activate it from Plans & Billing →</Link>
            </div>
          )}

          {!searching && searchError && (
            <p className="text-xs text-rose-600 mt-2">{searchError}</p>
          )}

          {!searching && !searchLocked && !searchError && searchedOnce && searchResults.length === 0 && (
            <p className="text-xs text-gray-400 mt-2">Koi partner nahi mila is keyword ke liye — thoda alag keyword try karo (jaise poori category ka naam).</p>
          )}

          {searchResults.length > 0 && (
            <div className="mt-3 space-y-2">
              {searchResults.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  disabled={referringPartnerId !== null}
                  onClick={() => referTo(p)}
                  className="w-full text-left px-4 py-3 rounded-xl border border-gray-200 hover:border-brand-400 hover:bg-brand-50 flex items-center justify-between disabled:opacity-60"
                >
                  <div>
                    <p className="font-medium text-gray-900">
                      {p.org_name} {p.preferred_partner && <span className="text-brand-600">★</span>}
                    </p>
                    <p className="text-xs text-gray-500">{p.category_name} · {p.city || 'City n/a'}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {p.is_my_partner && <Badge tone="verified">★ Your Partner</Badge>}
                    {p.verification_status === 'verified' ? <Badge tone="verified">verified</Badge> : <Badge tone="pending">pending</Badge>}
                    <span className="text-sm text-brand-700 font-medium">
                      {referringPartnerId === p.id ? 'Referring…' : 'Refer →'}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {error && <p className="text-sm text-rose-600">{error}</p>}
      </Card>
    </div>
  );
}
