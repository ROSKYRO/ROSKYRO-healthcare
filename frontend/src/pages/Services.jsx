import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';
import api from '../lib/api';
import { PageLoading, Button } from '../components/ui';
import { PublicHeader, PublicFooter } from '../components/PublicNav';

const PILLAR_STYLE = {
  grow: { emoji: '\u{1F680}', accent: 'text-amber-700', bg: 'bg-amber-50', ring: 'ring-amber-100' },
  manage: { emoji: '\u{2699}\u{FE0F}', accent: 'text-blue-700', bg: 'bg-blue-50', ring: 'ring-blue-100' },
  connect: { emoji: '\u{1F91D}', accent: 'text-teal-700', bg: 'bg-teal-50', ring: 'ring-teal-100' },
};

// The exact, curated CONNECT category taxonomy — the categories a
// healthcare business picks from when it lists itself as a partner (see
// customer/BecomePartner.jsx), mirrored here for the public marketing page.
const CONNECT_CATEGORIES = [
  { group: '\u{1F468}\u{200D}\u{2695}\u{FE0F} Specialist Referrals', items: ['Cardiologist', 'Orthopedic', 'Gynecologist', 'Pediatrician', 'Neurologist', 'Gastroenterologist', 'ENT Specialist', 'Dermatologist', 'Urologist', 'Oncologist', 'Psychiatrist', 'Other Specialists'] },
  { group: '\u{1F9EA} Diagnostics', items: ['Blood Test Labs', 'Pathology Labs', 'Home Sample Collection'] },
  { group: '\u{1FA7B} Imaging', items: ['X-Ray Centers', 'Ultrasound (USG) Centers', 'CT Scan Centers', 'MRI Centers'] },
  { group: '\u{1F3C3} Rehabilitation', items: ['Physiotherapy Centers', 'Rehabilitation Centers'] },
  { group: '\u{1F3E0} Home Healthcare', items: ['Physiotherapy at Home', 'Elder Care Services'] },
];

// Detailed sub-feature breakdown per pillar, shown below the dynamic
// plan-driven sections above -- this is deliberately static (not pulled
// from /plans) since it's a marketing-page breakdown of grouped
// capabilities, not the billing-relevant feature list.
const PILLAR_BREAKDOWN = [
  {
    code: 'grow', emoji: '\u{1F680}', title: 'GROW', accent: 'text-amber-700', bg: 'bg-amber-50',
    groups: [
      { name: 'AI Visibility Management', items: ['AI Search Visibility', 'Local SEO', 'GEO (Generative Engine Optimization)', 'AEO (Answer Engine Optimization)'] },
      { name: 'Google Business Profile', items: ['Optimization', 'Weekly Updates', 'Ranking Improvement'] },
      { name: 'Review Growth', items: ['QR Review System', 'Review Monitoring', 'Reputation Management'] },
      { name: 'Digital Marketing', items: ['Meta Ads', 'Google Ads', 'Social Media', 'Content Creation'] },
    ],
  },
  {
    code: 'manage', emoji: '\u{2699}\u{FE0F}', title: 'MANAGE', accent: 'text-blue-700', bg: 'bg-blue-50',
    groups: [
      { name: 'Day-to-day operations', items: ['CRM', 'Appointment Management', 'Billing', 'Patient Communication', 'Reports', 'Follow-up Automation'] },
    ],
  },
  {
    code: 'connect', emoji: '\u{1F91D}', title: 'CONNECT', accent: 'text-teal-700', bg: 'bg-teal-50',
    groups: [
      { name: 'Partner network', items: ['Referral Network', 'Diagnostic Partners', 'Imaging Partners', 'Rehabilitation Partners', 'Healthcare Collaborations'] },
    ],
  },
];

const INDUSTRIES = ['Doctors', 'Clinics', 'Hospitals', 'Dental Clinics', 'Diagnostic Labs', 'Imaging Centers', 'Physiotherapy', 'Rehabilitation Centers', 'Veterinary Clinics'];

const PILLAR_HIGHLIGHT = {
  grow: 'Every AI touchpoint here — review reply drafts, content — is human-reviewed before it ever reaches a patient or goes public. You approve, ROSKYRO executes.',
  manage: 'Includes QR self-booking: print one QR code at your front desk and patients book their own slot, pay your UPI directly, and queue up by token number — no extra staff needed.',
  connect: 'A patient referral is treated as marketing you do for your partner: the partner pays ROSKYRO a flat-rupee Marketing Fee per completed referral, and ROSKYRO shares a fixed percentage of that back with you, periodically, as a Marketing Fee Payout — with an invoice for every payout.',
};

function PillarSection({ plan, reverse }) {
  const style = PILLAR_STYLE[plan.code] || PILLAR_STYLE.grow;
  return (
    <div className={`grid md:grid-cols-2 gap-10 items-center py-14 ${reverse ? 'md:[&>*:first-child]:order-2' : ''}`}>
      <div>
        <div className={`h-12 w-12 rounded-2xl flex items-center justify-center text-2xl ${style.bg}`}>{style.emoji}</div>
        <h2 className="text-2xl font-bold text-gray-900 mt-4">{plan.name}</h2>
        <p className="text-gray-500 mt-1">{plan.tagline}</p>
        <p className="text-sm text-gray-600 mt-4 leading-relaxed">{style && PILLAR_HIGHLIGHT[plan.code]}</p>
        {plan.customer_promise && (
          <p className="text-sm italic text-gray-500 mt-4 border-l-2 border-gray-200 pl-3">"{plan.customer_promise}"</p>
        )}
        <p className="text-xs text-gray-400 mt-5">Best for</p>
        <p className="text-sm text-gray-700">{plan.best_for}</p>
        <div className="mt-6 flex items-center gap-4">
          <span className="text-2xl font-extrabold text-gray-900">₹{Number(plan.monthly_price).toLocaleString('en-IN')}<span className="text-sm font-normal text-gray-400">/month</span></span>
          <Link to="/pricing" className={`text-sm font-semibold ${style.accent}`}>See pricing details →</Link>
        </div>
      </div>
      <div className={`rounded-2xl border p-6 ${style.ring} ring-1 bg-white`}>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">What's included</p>
        <ul className="space-y-2.5">
          {(plan.features || []).map((f) => (
            <li key={f} className="flex items-start gap-2 text-sm text-gray-700">
              <span className={`mt-0.5 ${style.accent}`}>✓</span>
              <span>{f}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// Same service catalog, same pricing, two audiences -- a business tab and
// a partner tab (see Pricing.jsx for the full pricing-page toggle; mirrored
// here more lightly since this page's focus is what each service includes,
// not the checkout flow).
const AUDIENCES = [
  { key: 'business', label: 'For Businesses', endpoint: '/plans' },
  { key: 'partner', label: 'For Partners', endpoint: '/partner-plans' },
];

export default function Services() {
  const [audience, setAudience] = useState('business');
  const [plansByAudience, setPlansByAudience] = useState({});
  const [error, setError] = useState('');
  const plans = plansByAudience[audience];

  const load = (key) => {
    const a = AUDIENCES.find((x) => x.key === key);
    setError('');
    api.get(a.endpoint).then((res) => setPlansByAudience((prev) => ({
      ...prev, [key]: res.data.plans.filter((p) => !p.is_bundle && !p.is_addon).sort((x, y) => x.sort_order - y.sort_order),
    }))).catch(() => {
      setError('Could not load services. Please try again.');
    });
  };

  useEffect(() => { if (!plansByAudience[audience]) load(audience); }, [audience]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen bg-gray-50">
      <PublicHeader />

      <section className="max-w-3xl mx-auto px-6 pt-8 pb-8 text-center">
        <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-brand-50 text-brand-700 rounded-full px-3 py-1 mb-5">
          What ROSKYRO Actually Does
        </p>
        <h1 className="text-3xl md:text-4xl font-extrabold text-gray-900 tracking-tight">
          Three services. Two ways to work with ROSKYRO.
        </h1>
        <p className="mt-4 text-gray-500">
          Get more patients, run your day-to-day without the chaos, and build a trusted network of partners —
          as a healthcare business, or as a CONNECT partner. Each is its own subscription, so you
          only pay for what you actually need.
        </p>
      </section>

      <div className="flex items-center justify-center gap-2 mb-8">
        {AUDIENCES.map((a) => (
          <button
            key={a.key}
            type="button"
            onClick={() => setAudience(a.key)}
            className={clsx(
              'px-5 py-2 rounded-full text-sm font-semibold border transition',
              audience === a.key ? 'bg-brand-600 border-brand-600 text-white' : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300'
            )}
          >
            {a.label}
          </button>
        ))}
      </div>

      <section className="max-w-5xl mx-auto px-6 pb-8">
        {error && !plans ? (
          <div className="text-center py-16">
            <p className="text-sm text-rose-600">{error}</p>
            <Button size="sm" variant="secondary" className="mt-4" onClick={() => load(audience)}>Retry</Button>
          </div>
        ) : !plans ? <PageLoading /> : (
          <div className="divide-y divide-gray-100">
            {plans.map((plan, i) => (
              <PillarSection key={plan.code} plan={plan} reverse={i % 2 === 1} />
            ))}
          </div>
        )}
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-16">
        <h2 className="text-2xl font-bold text-gray-900 text-center">What's Inside Each Pillar</h2>
        <p className="text-gray-500 text-center mt-2 max-w-xl mx-auto">
          A closer look at exactly what each subscription covers.
        </p>
        <div className="mt-8 space-y-6">
          {PILLAR_BREAKDOWN.map((p) => (
            <div key={p.code} className="bg-white border border-gray-200 rounded-2xl p-6 md:p-8">
              <div className="flex items-center gap-2 mb-4">
                <div className={`h-9 w-9 rounded-xl flex items-center justify-center text-lg ${p.bg}`}>{p.emoji}</div>
                <h3 className={`font-bold text-lg ${p.accent}`}>{p.title}</h3>
              </div>
              <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
                {p.groups.map((g) => (
                  <div key={g.name}>
                    <p className="text-xs font-semibold text-gray-900">{g.name}</p>
                    <ul className="mt-2 space-y-1">
                      {g.items.map((i) => (
                        <li key={i} className="text-xs text-gray-500">{i}</li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-16">
        <div className="bg-white border border-gray-200 rounded-2xl p-8 md:p-10 text-center">
          <h2 className="text-xl font-bold text-gray-900">Industries We Work With</h2>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            {INDUSTRIES.map((a) => (
              <span key={a} className="text-sm bg-brand-50 text-brand-700 px-3 py-1.5 rounded-full font-medium">{a}</span>
            ))}
          </div>
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-16">
        <div className="border border-gray-200 rounded-2xl p-8 md:p-12">
          <div className="text-center max-w-2xl mx-auto">
            <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-teal-50 text-teal-700 rounded-full px-3 py-1 mb-4">
              {'\u{1F91D}'} CONNECT
            </p>
            <h3 className="text-2xl font-bold text-gray-900">Verified Healthcare Service Partners</h3>
            <p className="mt-3 text-gray-600">
              Connect with trusted specialists, diagnostic labs, imaging centers, rehabilitation providers, and home
              healthcare services—all from one platform. Listing your business is free — you choose your own
              partners, on your own terms.
            </p>
          </div>
          <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {CONNECT_CATEGORIES.map((g) => (
              <div key={g.group} className="rounded-xl bg-gray-50 border border-gray-100 p-5">
                <p className="font-semibold text-gray-900 text-sm">{g.group}</p>
                <ul className="mt-3 space-y-1.5">
                  {g.items.map((i) => (
                    <li key={i} className="text-sm text-gray-600">{i}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <div className="text-center mt-8">
            <Link to="/register" className="inline-block bg-brand-600 text-white font-semibold px-6 py-3 rounded-xl hover:bg-brand-700">
              List your business for free
            </Link>
          </div>
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-20">
        <div className="bg-brand-950 text-white rounded-2xl p-8 md:p-12 text-center">
          <h3 className="text-xl font-bold">Not sure which one you need?</h3>
          <p className="mt-3 text-brand-100 max-w-2xl mx-auto">
            Most businesses start with one pillar and add more as they grow. Take all three together as
            ROSKYRO Complete and save — see the exact numbers on the pricing page.
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-4">
            <Link to="/pricing" className="inline-block bg-white text-brand-900 font-semibold px-6 py-3 rounded-xl hover:bg-brand-50">
              See Plans
            </Link>
            <Link to="/contact?reason=demo" className="inline-block border border-white/30 font-semibold px-6 py-3 rounded-xl hover:bg-white/10">
              Book Demo
            </Link>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
