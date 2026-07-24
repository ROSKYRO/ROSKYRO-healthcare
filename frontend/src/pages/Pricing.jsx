import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import api from '../lib/api';
import PricingCards from '../components/PricingCards';
import { PageLoading } from '../components/ui';
import { PublicHeader, PublicFooter } from '../components/PublicNav';
import FaqList from '../components/FaqList';

const PRICING_FAQS = [
  { q: 'Is there any contract?', a: 'No. Every ROSKYRO subscription is month-to-month by default (an annual plan is available at a discount). There is no long-term lock-in and no cancellation penalty.' },
  { q: 'Can I cancel anytime?', a: 'Yes, from your dashboard billing settings, effective at the end of your current billing cycle.' },
  { q: 'Can I take just one pillar?', a: 'Yes — GROW, MANAGE and CONNECT are each priced and billed separately. Take one, two, or bundle all three as Complete Platform to save.' },
  { q: 'What payment methods do you accept?', a: 'Subscriptions are paid to ROSKYRO directly via UPI. Referral commission under CONNECT, if any, is paid directly between you and your partner.' },
  { q: 'Is there a setup fee?', a: 'No hidden setup fee — onboarding and training are included in your subscription.' },
];

export default function Pricing() {
  const [plans, setPlans] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.get('/plans').then((res) => setPlans(res.data.plans));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50">
      <PublicHeader />

      <section className="max-w-3xl mx-auto px-6 pt-8 pb-12 text-center">
        <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-brand-50 text-brand-700 rounded-full px-3 py-1 mb-5">
          Monthly Subscription · Annual Membership · Cancel Anytime
        </p>
        <h1 className="text-3xl md:text-4xl font-extrabold text-gray-900 tracking-tight">
          Three pillars. One healthcare growth platform.
        </h1>
        <p className="mt-4 text-gray-500">
          ROSKYRO is a SaaS + Managed Services subscription, not a one-time purchase — your team keeps working
          every month you stay subscribed. Agar aapko sirf patient growth chahiye, sirf operations simplify
          karne hain, ya sirf ek trusted partner network chahiye — alag se le sakte hain. Sab kuch ek saath
          chahiye? Complete Platform bundle le kar bachaiye. No long-term contract — cancel any time.
        </p>
      </section>

      <section className="max-w-6xl mx-auto px-6 pb-16">
        {!plans ? <PageLoading /> : (
          <PricingCards
            plans={plans}
            ctaLabel="Get Started"
            onSelect={() => navigate('/register')}
          />
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
