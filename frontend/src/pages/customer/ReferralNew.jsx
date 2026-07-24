import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { canCreateReferrals } from '../../lib/referralRights';
import { Card, Button, Input, Select, Textarea, EmptyState } from '../../components/ui';

export default function ReferralNew() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [categories, setCategories] = useState([]);
  const [category, setCategory] = useState('');
  const [city, setCity] = useState('');
  const [partners, setPartners] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [form, setForm] = useState({
    partnerId: '', patientName: '', patientPhone: '', patientAge: '', patientGender: '',
    serviceRequested: '', clinicalNotes: '', urgency: 'routine',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get('/partners/categories').then((res) => setCategories(res.data.categories));
  }, []);

  useEffect(() => {
    if (!category) { setPartners([]); return; }
    api.get('/partners', { params: { category, city: city || undefined, verifiedOnly: true } }).then((res) => setPartners(res.data.partners));
    api.get('/partners/recommendations', { params: { category, city: city || undefined } }).then((res) => setRecommendations(res.data.recommendations));
  }, [category, city]);

  function set(key) {
    return (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const { data } = await api.post('/referrals', {
        ...form,
        patientAge: form.patientAge ? Number(form.patientAge) : undefined,
      });
      navigate(`/app/referrals/${data.referral.id}`);
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not create referral.');
    } finally {
      setLoading(false);
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
        <p className="text-sm text-gray-500 mt-1">Refer a patient to a trusted partner in the ROSKYRO network. We'll generate the referral slip and QR code automatically.</p>
      </div>

      <Card className="p-6 space-y-5">
        <div className="grid grid-cols-2 gap-4">
          <Select label="Service category" value={category} onChange={(e) => { setCategory(e.target.value); setForm((f) => ({ ...f, partnerId: '' })); }}>
            <option value="">Select a category</option>
            {categories.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
          </Select>
          <Input label="City (optional filter)" value={city} onChange={(e) => setCity(e.target.value)} placeholder="Pune" />
        </div>

        {recommendations.length > 0 && (
          <div className="bg-brand-50 border border-brand-100 rounded-xl p-4">
            <p className="text-xs font-semibold text-brand-700 uppercase tracking-wide mb-2">AI-suggested partners</p>
            <div className="space-y-2">
              {recommendations.map((r) => (
                <button
                  type="button"
                  key={r.id}
                  onClick={() => setForm((f) => ({ ...f, partnerId: r.id }))}
                  className={`w-full text-left text-sm px-3 py-2 rounded-lg border ${form.partnerId === r.id ? 'border-brand-600 bg-white' : 'border-transparent hover:bg-white/60'}`}
                >
                  <span className="font-medium text-gray-900">{r.org_name}</span>
                  <span className="text-gray-400"> — {r.city} · score {Math.round(r.ai_score)}</span>
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-400 mt-2">A ROSKYRO team member or you make the final call — this is a suggestion, not an auto-assignment.</p>
          </div>
        )}

        <Select label="Partner" required value={form.partnerId} onChange={set('partnerId')} disabled={!category}>
          <option value="">{category ? 'Select a partner' : 'Choose a category first'}</option>
          {partners.map((p) => (
            <option key={p.id} value={p.id}>{p.org_name} — {p.city} {p.preferred_partner ? '★ preferred' : ''}</option>
          ))}
        </Select>

        <div className="grid grid-cols-2 gap-4">
          <Input label="Patient name" required value={form.patientName} onChange={set('patientName')} />
          <Input label="Patient phone" value={form.patientPhone} onChange={set('patientPhone')} />
          <Input label="Patient age" type="number" value={form.patientAge} onChange={set('patientAge')} />
          <Select label="Gender" value={form.patientGender} onChange={set('patientGender')}>
            <option value="">—</option>
            <option>Male</option>
            <option>Female</option>
            <option>Other</option>
          </Select>
        </div>

        <Input label="Service requested" required value={form.serviceRequested} onChange={set('serviceRequested')} placeholder="e.g. MRI Brain" />
        <Textarea label="Clinical notes (optional)" rows={3} value={form.clinicalNotes} onChange={set('clinicalNotes')} />

        <Select label="Urgency" value={form.urgency} onChange={set('urgency')}>
          <option value="routine">Routine</option>
          <option value="urgent">Urgent</option>
          <option value="emergency">Emergency</option>
        </Select>

        {error && <p className="text-sm text-rose-600">{error}</p>}

        <div className="flex gap-3">
          <Button onClick={handleSubmit} disabled={loading || !form.partnerId}>{loading ? 'Sending…' : 'Send Referral'}</Button>
        </div>
      </Card>
    </div>
  );
}
