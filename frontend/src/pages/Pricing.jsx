import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import api from '../lib/api';
import PricingCards from '../components/PricingCards';
import { PageLoading, Button, formatCurrency } from '../components/ui';
import { PublicHeader, PublicFooter } from '../components/PublicNav';
import FaqList from '../components/FaqList';

const PRICING_FAQS = [
  { q: 'Is there any contract?', a: 'No. Every ROSKYRO subscription is month-to-month by default (an annual plan is available at a discount). There is no long-term lock-in and no cancellation penalty.' },
  { q: 'Can I cancel anytime?', a: 'Yes, from your dashboard billing settings, effective at the end of your current billing cycle.' },
  { q: 'Can I take just one pillar?', a: 'Yes — GROW, MANAGE and Networking Marketing are each priced and billed separately. Take one, two, or bundle all three as Complete Platform to save.' },
  { q: 'What payment methods do you accept?', a: 'Subscriptions are paid to ROSKYRO directly via UPI. Under Networking Marketing, a partner pays ROSKYRO a flat-rupee Marketing Fee per completed referral, and ROSKYRO periodically pays a fixed percentage of that back to the referring business as a Marketing Fee Payout.' },
  { q: 'Is there a setup fee?', a: 'No hidden setup fee — onboarding and training are included in your subscription.' },
];

// Same three services (GROW / MANAGE / Networking Marketing), two different
// audiences with two different price catalogs -- a healthcare business
// pays business pricing, a Networking Marketing partner pays partner
// pricing. Each side also has its own "buy 2, get the 3rd free" bundle
// bonus (mirror images of each other) plus the optional Reel Making add-on.
const AUDIENCES = [
  { key: 'business', label: 'For Businesses', endpoint: '/plans', registerPath: '/register', bonusText: 'Activate MANAGE + GROW together and Networking Marketing (CONNECT) is unlocked free, as a bonus earning service.' },
  { key: 'partner', label: 'For Partners', endpoint: '/partner-plans', registerPath: '/contact?reason=become-partner', bonusText: 'Activate GROW + Networking Marketing (CONNECT) together and MANAGE is unlocked free.' },
];

export default function Pricing() {
  const [audience, setAudience] = useState('business');
  const [plansByAudience, setPlansByAudience] = useState({});
  const [error, setError] = useState('');
  const navigate = useNavigate();
  const current = AUDIENCES.find((a) => a.key === audience);
  const plans = plansByAudience[audience];

  const load = (key) => {
    const a = AUDIENCES.find((x) => x.key === key);
    setError('');
    api.get(a.endpoint).then((res) => setPlansByAudience((prev) => ({ ...prev, [key]: res.data.plans }))).catch(() => {
      setError('Could not load plans. Please try again.');
    });
  };

  useEffect(() => { if (!plansByAudience[audience]) load(audience); }, [audience]); // eslint-disable-line react-hooks/exhaustive-deps

  const addon = plans?.find((p) => p.is_addon);

  return (
    <div className="min-h-screen bg-gray-50">
      <PublicHeader />

      <section className="max-w-3xl mx-auto px-6 pt-8 pb-8 text-center">
        <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-brand-50 text-brand-700 rounded-full px-3 py-1 mb-5">
          Monthly Subscription · Annual Membership · Cancel Anytime
        </p>
        <h1 className="text-3xl md:text-4xl font-extrabold text-gray-900 tracking-tight">
          Three services. Two ways to work with ROSKYRO.
        </h1>
        <p className="mt-4 text-gray-500">
          The exact same GROW / MANAGE / Networking Marketing services, at the exact same pricing — as a healthcare
          business growing patients and operations, or as a Networking Marketing partner growing referral volume.
          No long-term contract — cancel any time.
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

      <section className="max-w-6xl mx-auto px-6 pb-8">
        {error && !plans ? (
          <div className="text-center py-16">
            <p className="text-sm text-rose-600">{error}</p>
            <Button size="sm" variant="secondary" className="mt-4" onClick={() => load(audience)}>Retry</Button>
          </div>
        ) : !plans ? <PageLoading /> : (
          <>
            <div className="max-w-3xl mx-auto mb-6 text-center bg-teal-50 border border-teal-100 rounded-xl px-5 py-3">
              <p className="text-sm text-gray-700">{'\u{1F381}'} <span className="font-semibold">Bonus:</span> {current.bonusText}</p>
            </div>
            <PricingCards
              plans={plans}
              ctaLabel="Get Started"
              onSelect={() => navigate(current.registerPath)}
            />
            {addon && (
              <div className="max-w-2xl mx-auto mt-8 rounded-2xl border-2 border-dashed border-gray-200 bg-white p-6 text-center">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Optional Add-on</p>
                <h3 className="text-lg font-bold text-gray-900 mt-1">{addon.name}</h3>
                <p className="text-sm text-gray-500 mt-1">{addon.tagline}</p>
                <p className="text-2xl font-extrabold text-gray-900 mt-3">
                  {formatCurrency(addon.monthly_price)}<span className="text-sm font-normal text-gray-400">/month</span>
                </p>
                <p className="text-xs text-gray-400 mt-2">Only available alongside {(addon.requires_pillar || 'GROW').toUpperCase()}.</p>
              </div>
            )}
          </>
        )}
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-16">
        <div className="border-2 border-dashed border-gray-300 rounded-2xl p-8 md:p-12 text-center bg-white">
          <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-gray-100 text-gray-600 rounded-full px-3 py-1 mb-4">
            Enterprise
          </p>
          <h2 className="text-xl font-bold text-gray-900">Running a hospital chain or multi-branch network?</h2>
          <p className="mt-3 text-gray-500 max-w-xl mx-auto">
            Custom pricing, multi-branch rollout, dedicated onboarding and a dedicated account manager — built
            around how your organization actually runs.
          </p>
          <Link to="/contact?reason=enterprise" className="inline-block mt-6 bg-brand-600 text-white font-semibold px-6 py-3 rounded-xl hover:bg-brand-700">
            Talk to Sales
          </Link>
        </div>
      </section>

      <section className="max-w-3xl mx-auto px-6 pb-16">
        <h2 className="text-2xl font-bold text-gray-900 text-center">Pricing FAQ</h2>
        <div className="mt-8">
          <FaqList items={PRICING_FAQS} />
        </div>
      </section>

      <section className="max-w-3xl mx-auto px-6 pb-20 text-center">
        <div className="bg-brand-950 text-white rounded-2xl p-8 md:p-12">
          <h3 className="text-xl font-bold">Not sure which plan fits your business?</h3>
          <p className="mt-3 text-brand-100 max-w-xl mx-auto">Talk to us — we'll help you pick the right pillars.</p>
          <Link to="/contact?reason=demo" className="inline-block mt-6 bg-white text-brand-900 font-semibold px-6 py-3 rounded-xl hover:bg-brand-50">
            Book Free Demo
          </Link>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
