import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../../lib/api';
import { Card, CardHeader, Button, Input, Select, PageLoading } from '../../components/ui';

const EMPTY_SERVICE = { name: '', price: '', priceUnit: 'per service' };

export default function BecomePartner() {
  const [loading, setLoading] = useState(true);
  const [categories, setCategories] = useState([]);
  const [existing, setExisting] = useState(null);

  const [categorySlug, setCategorySlug] = useState('');
  const [coverageArea, setCoverageArea] = useState('');
  const [coverageCities, setCoverageCities] = useState('');
  const [turnaroundTime, setTurnaroundTime] = useState('');
  const [contactPerson, setContactPerson] = useState('');
  const [contactPhone, setContactPhone] = useState('');
  const [contactEmail, setContactEmail] = useState('');
  const [services, setServices] = useState([{ ...EMPTY_SERVICE }]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [submitted, setSubmitted] = useState(null);

  useEffect(() => {
    Promise.all([
      api.get('/partners/categories'),
      api.get('/partners/me').then((r) => r.data.partner).catch(() => null),
    ]).then(([catRes, me]) => {
      setCategories(catRes.data.categories);
      setExisting(me);
      setLoading(false);
    });
  }, []);

  // Group categories by their group_name for a grouped <optgroup> picker —
  // matches the curated CONNECT taxonomy (Specialist Referrals, Diagnostics,
  // Imaging, Rehabilitation, Home Healthcare).
  const grouped = categories.reduce((acc, c) => {
    const key = c.group_name || 'Other';
    (acc[key] = acc[key] || []).push(c);
    return acc;
  }, {});

  function updateService(idx, field, value) {
    setServices((prev) => prev.map((s, i) => (i === idx ? { ...s, [field]: value } : s)));
  }

  function addService() {
    setServices((prev) => [...prev, { ...EMPTY_SERVICE }]);
  }

  function removeService(idx) {
    setServices((prev) => prev.filter((_, i) => i !== idx));
  }

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const cleanServices = services
        .filter((s) => s.name.trim())
        .map((s) => ({ name: s.name.trim(), price: s.price ? Number(s.price) : null, priceUnit: s.priceUnit || 'per service' }));

      const res = await api.post('/partners/register', {
        categorySlug,
        coverageArea: coverageArea || null,
        coverageCities: coverageCities ? coverageCities.split(',').map((c) => c.trim()).filter(Boolean) : null,
        turnaroundTime: turnaroundTime || null,
        contactPerson: contactPerson || null,
        contactPhone: contactPhone || null,
        contactEmail: contactEmail || null,
        services: cleanServices.length ? cleanServices : null,
      });
      setSubmitted(res.data.partner);
    } catch (err) {
      setError(err?.response?.data?.error || 'Could not submit your partner application.');
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <PageLoading />;

  const alreadyPartner = existing || submitted;

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Become a Partner</h1>
        <p className="text-sm text-gray-500 mt-1">
          List your business on ROSKYRO CONNECT for free. Doctors, clinics and hospitals across the network can then
          discover you and choose to send you referrals — the choice of who to partner with is always theirs.
        </p>
      </div>

      {alreadyPartner ? (
        <Card className="p-6">
          <p className="text-base font-semibold text-gray-900">
            {alreadyPartner.verification_status === 'verified' ? "You're a verified CONNECT partner ✅" : "Application submitted ✓"}
          </p>
          <p className="text-sm text-gray-500 mt-2">
            {alreadyPartner.verification_status === 'verified'
              ? 'Your listing is live in the Partner Directory. Businesses can now discover you and choose to refer patients your way.'
              : 'Your free CONNECT listing is pending verification by the ROSKYRO team — this is usually quick. You’ll be notified as soon as it’s approved.'}
          </p>
          <Link to="/app/partners" className="text-sm text-brand-700 font-medium mt-4 inline-block">
            View the Partner Directory →
          </Link>
        </Card>
      ) : (
        <Card>
          <CardHeader
            title="Free Partner Listing"
            subtitle="No charge to list yourself. Pick the category that best describes your service — this is the exact, curated CONNECT category list."
          />
          <form onSubmit={submit} className="px-5 pb-5 space-y-4">
            <Select label="Category" value={categorySlug} onChange={(e) => setCategorySlug(e.target.value)} required>
              <option value="">Select a category…</option>
              {Object.entries(grouped).map(([groupName, cats]) => (
                <optgroup key={groupName} label={groupName}>
                  {cats.map((c) => (
                    <option key={c.slug} value={c.slug}>{c.name}</option>
                  ))}
                </optgroup>
              ))}
            </Select>

            <div className="grid sm:grid-cols-2 gap-4">
              <Input label="Coverage area" value={coverageArea} onChange={(e) => setCoverageArea(e.target.value)} placeholder="e.g. Pune and surrounding areas" />
              <Input label="Coverage cities (comma separated)" value={coverageCities} onChange={(e) => setCoverageCities(e.target.value)} placeholder="Pune, Pimpri-Chinchwad" />
            </div>

            <Input label="Typical turnaround time" value={turnaroundTime} onChange={(e) => setTurnaroundTime(e.target.value)} placeholder="e.g. Same day, 24 hrs" />

            <div className="grid sm:grid-cols-3 gap-4">
              <Input label="Contact person" value={contactPerson} onChange={(e) => setContactPerson(e.target.value)} placeholder="Defaults to your name" />
              <Input label="Contact phone" value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} />
              <Input label="Contact email" value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} placeholder="Defaults to your account email" />
            </div>

            <div>
              <p className="block text-sm font-medium text-gray-700 mb-2">Services you offer (optional)</p>
              <div className="space-y-2">
                {services.map((s, idx) => (
                  <div key={idx} className="flex gap-2 items-start">
                    <Input className="flex-1" placeholder="Service name" value={s.name} onChange={(e) => updateService(idx, 'name', e.target.value)} />
                    <Input className="w-32" type="number" min="0" placeholder="Price ₹" value={s.price} onChange={(e) => updateService(idx, 'price', e.target.value)} />
                    {services.length > 1 && (
                      <Button type="button" variant="ghost" size="sm" onClick={() => removeService(idx)}>✕</Button>
                    )}
                  </div>
                ))}
              </div>
              <Button type="button" variant="secondary" size="sm" className="mt-2" onClick={addService}>+ Add another service</Button>
            </div>

            {error && <p className="text-sm text-rose-600">{error}</p>}

            <div className="pt-2 border-t border-gray-100">
              <Button type="submit" disabled={busy || !categorySlug}>{busy ? 'Submitting…' : 'Submit Free Listing'}</Button>
              <p className="text-xs text-gray-400 mt-2">
                Your listing goes live after a quick ROSKYRO verification. It's always free — there's no charge to join CONNECT as a partner.
              </p>
            </div>
          </form>
        </Card>
      )}
    </div>
  );
}
