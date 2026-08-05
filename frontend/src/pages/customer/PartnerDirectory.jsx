import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../../lib/api';
import { useAuth } from '../../context/AuthContext';
import { canCreateReferrals } from '../../lib/referralRights';
import { Card, Badge, PageLoading, Select, Input, EmptyState, Button, formatCurrency } from '../../components/ui';

export default function PartnerDirectory() {
  const { user } = useAuth();
  const [categories, setCategories] = useState([]);
  const [category, setCategory] = useState('');
  const [q, setQ] = useState('');
  const [sortBy, setSortBy] = useState('default');
  const [partners, setPartners] = useState(null);
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    api.get('/partners/categories').then((res) => setCategories(res.data.categories)).catch(() => {});
  }, []);

  // Debounced -- without this, every keystroke in the search box fired its
  // own GET /partners request (racing with the previous one), hammering
  // the backend and making the list flicker/jump on fast typing.
  useEffect(() => {
    setLocked(false);
    setError('');
    const t = setTimeout(() => {
      api.get('/partners', { params: { category: category || undefined, q: q || undefined } })
        .then((res) => setPartners(res.data.partners))
        .catch((err) => {
          // Browsing the full directory needs the CONNECT plan (unlike free
          // self-registration via "Become a Partner") — show an upgrade
          // prompt instead of letting the request crash the page.
          if (err?.response?.status === 402) {
            setLocked(true);
            setPartners([]);
          } else {
            // Any other failure (network blip, 5xx) previously left
            // `partners` at null forever -> a permanent loading spinner
            // with no way out. Show a retryable error instead.
            setError(err?.response?.data?.error || 'Could not load partners. Please try again.');
            setPartners([]);
          }
        });
    }, 300);
    return () => clearTimeout(t);
  }, [category, q]);

  const sortedPartners = !partners ? null : sortBy === 'bonus'
    ? [...partners].sort((a, b) => (b.referral_bonus_amount ?? -1) - (a.referral_bonus_amount ?? -1))
    : partners;

  if (!canCreateReferrals(user)) {
    return (
      <EmptyState
        title="Your business type can't choose/create referrals."
        subtitle="Referral bhejne (partner choose karne) ka right sirf Clinic, Hospital aur Eye Hospital business types ko hai. Aap phir bhi khud ko ek CONNECT partner ke roop mein list kar sakte hain, taaki doosre businesses aapko refer kar sakein."
        action={<Link to="/app/become-partner"><Button size="sm">Become a Partner</Button></Link>}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Partner Directory</h1>
          <p className="text-sm text-gray-500 mt-1">Trusted diagnostic labs, imaging centres, specialists and more — verified by ROSKYRO. Har partner ka apna flat ₹ Marketing Fee hota hai (jo wo har completed referral par ROSKYRO ko pay karta hai) — partner khud set kare ya na kare, category ke hisab se ek default fee yahan dikhta hai — jitna zyada collection hoga, utna hi zyada aapka Marketing Fee Payout share bhi banega.</p>
        </div>
        <Link to="/app/become-partner" className="shrink-0 text-sm font-medium text-brand-700 border border-brand-200 bg-brand-50 rounded-lg px-3 py-2 hover:bg-brand-100">
          List your business — it's free →
        </Link>
      </div>

      <div className="flex flex-wrap gap-3">
        <Select value={category} onChange={(e) => setCategory(e.target.value)} className="max-w-xs">
          <option value="">All categories</option>
          {Object.entries(
            categories.reduce((acc, c) => {
              const key = c.group_name || 'Other';
              (acc[key] = acc[key] || []).push(c);
              return acc;
            }, {})
          ).map(([groupName, cats]) => (
            <optgroup key={groupName} label={groupName}>
              {cats.map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
            </optgroup>
          ))}
        </Select>
        <Input placeholder="Search by name…" value={q} onChange={(e) => setQ(e.target.value)} className="max-w-xs" />
        <Select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="max-w-xs">
          <option value="default">Sort: Recommended</option>
          <option value="bonus">Sort: Highest Marketing Fee first</option>
        </Select>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      {!sortedPartners ? <PageLoading /> : locked ? (
        <EmptyState
          title="Browsing the full Partner Directory needs the CONNECT plan."
          subtitle="You can still list your own business as a partner for free — other businesses will be able to find and refer to you either way."
          action={<Link to="/app/plans"><Button size="sm">Activate CONNECT</Button></Link>}
        />
      ) : sortedPartners.length === 0 ? (
        <EmptyState title="No partners found." subtitle="Try a different category or search term." />
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedPartners.map((p) => (
            <Card key={p.id} className="p-5">
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-semibold text-gray-900">{p.org_name}</p>
                  <p className="text-xs text-gray-400">{p.category_name} · {p.city}</p>
                </div>
                {p.preferred_partner && <Badge tone="verified">Preferred</Badge>}
              </div>
              <div className="mt-3 flex items-center gap-2 text-xs text-gray-500">
                <Badge tone={p.verification_status}>{p.verification_status}</Badge>
                {p.rating_avg > 0 && <span>★ {p.rating_avg}</span>}
              </div>
              <p className="text-sm text-gray-500 mt-2">{p.turnaround_time || 'Turnaround time not set'}</p>
              {p.referral_bonus_amount != null ? (
                <p className="text-sm font-semibold text-brand-700 mt-3">
                  💰 {formatCurrency(p.referral_bonus_amount)} Marketing Fee per referral
                </p>
              ) : (
                <p className="text-xs text-gray-400 mt-3">Marketing Fee not set by this partner yet</p>
              )}
              <Link to="/app/referrals/new" className="text-sm text-brand-700 font-medium mt-3 inline-block">Refer a patient →</Link>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
