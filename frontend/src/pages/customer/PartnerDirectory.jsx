import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../../lib/api';
import { Card, Badge, PageLoading, Select, Input, EmptyState, Button } from '../../components/ui';

export default function PartnerDirectory() {
  const [categories, setCategories] = useState([]);
  const [category, setCategory] = useState('');
  const [q, setQ] = useState('');
  const [sortBy, setSortBy] = useState('default');
  const [partners, setPartners] = useState(null);
  const [locked, setLocked] = useState(false);

  useEffect(() => {
    api.get('/partners/categories').then((res) => setCategories(res.data.categories)).catch(() => {});
  }, []);

  useEffect(() => {
    setLocked(false);
    api.get('/partners', { params: { category: category || undefined, q: q || undefined } })
      .then((res) => setPartners(res.data.partners))
      .catch((err) => {
        // Browsing the full directory needs the CONNECT plan (unlike free
        // self-registration via "Become a Partner") — show an upgrade
        // prompt instead of letting the request crash the page.
        if (err?.response?.status === 402) {
          setLocked(true);
          setPartners([]);
        }
      });
  }, [category, q]);

  const sortedPartners = !partners ? null : sortBy === 'commission'
    ? [...partners].sort((a, b) => (b.commission_rate_percentage ?? -1) - (a.commission_rate_percentage ?? -1))
    : partners;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Partner Directory</h1>
          <p className="text-sm text-gray-500 mt-1">Trusted diagnostic labs, imaging centres, specialists and more — verified by ROSKYRO. Har partner apni commission khud set karta hai, jo yahan dikhti hai.</p>
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
          <option value="commission">Sort: Highest commission first</option>
        </Select>
      </div>

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
              {p.commission_rate_percentage != null ? (
                <p className="text-sm font-semibold text-brand-700 mt-3">
                  💰 {p.commission_rate_percentage}% commission per referral
                </p>
              ) : (
                <p className="text-xs text-gray-400 mt-3">Commission rate not set by this partner yet</p>
              )}
              <Link to="/app/referrals/new" className="text-sm text-brand-700 font-medium mt-3 inline-block">Refer a patient →</Link>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
