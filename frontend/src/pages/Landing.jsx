import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/api';
import { PublicHeader, PublicFooter } from '../components/PublicNav';
import FaqList from '../components/FaqList';
import { FAQ_HOMEPAGE } from '../data/faq';

// Fixed: prices here used to be hardcoded strings baked straight into the
// bundle ('14,999' / '9,999' / '4,999'), while Pricing.jsx and Services.jsx
// both correctly fetch live pricing from GET /plans. Prices are
// admin-editable at runtime via PATCH /plans/{code} (see
// internal/PricingManagement.jsx) specifically so they CAN change without a
// frontend redeploy -- the moment an admin updated a plan's price, this,
// the highest-traffic page on the site, would keep showing the old number
// while /pricing showed the correct one. Static copy (title, subtitle,
// promise, feature bullets, emoji) stays here since that's genuinely
// content, not billing data; only the price itself now comes from the live
// catalog, matched by `code`.
const PILLARS = [
  {
    code: 'grow', emoji: '\u{1F680}', title: 'GROW', subtitle: 'Get More Patients',
    promise: '"Hum marketing nahi, patient growth par kaam karte hain."',
    items: ['AI Visibility Management', 'Google Business Profile', 'Review Growth', 'SEO & AI Search', 'Social Media Marketing'],
  },
  {
    code: 'manage', emoji: '\u{2699}\u{FE0F}', title: 'MANAGE', subtitle: 'Run Your Business Efficiently',
    promise: '"Hum aapke operations ko simple aur organized banate hain."',
    items: ['Appointment Management', 'Patient CRM', 'Billing', 'Patient Communication', 'Reports'],
  },
  {
    code: 'connect', emoji: '\u{1F91D}', title: 'Networking Marketing', subtitle: "Grow Through India's Healthcare Network",
    promise: '"Hum aapko trusted healthcare partners se jodte hain."',
    items: ['Referral Network', 'Diagnostic Partners', 'Imaging Centers', 'Rehab Partners', 'Home Healthcare'],
  },
];

const TRUSTED_BY = ['Clinics', 'Hospitals', 'Diagnostic Labs', 'Imaging Centers', 'Physiotherapy Centers'];

const INDUSTRIES = ['Doctors', 'Clinics', 'Hospitals', 'Dental Clinics', 'Diagnostic Labs', 'Imaging Centers', 'Physiotherapy', 'Rehabilitation Centers', 'Veterinary Clinics'];

const WHY_ROSKYRO = [
  { emoji: '\u{1FA7A}', title: 'Healthcare Industry Specialist', body: 'Built only for healthcare businesses — not a generic marketing tool adapted after the fact.' },
  { emoji: '\u{1F916}', title: 'AI Powered', body: 'AI does the heavy lifting on visibility, content and operations — so your team does not have to.' },
  { emoji: '\u{1F91D}', title: 'Human Support', body: 'A real team backs every AI output — you always have a person to call, not just a chatbot.' },
  { emoji: '\u{1F5A5}\u{FE0F}', title: 'One Platform', body: 'Growth, operations and partner network — one login instead of five disconnected tools.' },
  { emoji: '\u{1F4B0}', title: 'Affordable', body: 'Priced per pillar so you only pay for what you actually use, with bundle savings if you take all three.' },
  { emoji: '\u{26A1}', title: 'Fast Setup', body: 'Guided onboarding gets your account live and your team trained in days, not months.' },
];

const HOW_IT_WORKS = [
  { step: '1', title: 'Book Demo', body: 'Tell us about your business and what you want to fix or grow first.' },
  { step: '2', title: 'Business Analysis', body: 'We review your current visibility, operations and network gaps.' },
  { step: '3', title: 'Setup', body: 'Your account is configured, your team trained, and your pillars switched on.' },
  { step: '4', title: 'Growth Starts', body: 'AI + our team get to work — you approve outcomes and track results.' },
];

export default function Landing() {
  const [priceByCode, setPriceByCode] = useState({});

  useEffect(() => {
    api.get('/plans').then((res) => {
      const map = {};
      for (const p of res.data.plans || []) map[p.code] = p.monthly_price;
      setPriceByCode(map);
    }).catch(() => {
      // Best-effort only -- if this fails, the price line below just
      // doesn't render rather than showing a stale/fake number. The rest
      // of the homepage doesn't depend on pricing data.
    });
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-b from-brand-950 to-brand-900 text-white">
      <PublicHeader dark />

      <section className="max-w-4xl mx-auto px-6 pt-16 pb-20 text-center">
        <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-white/10 rounded-full px-3 py-1 mb-6">
          AI Business Software for Healthcare
        </p>
        <h1 className="text-4xl md:text-5xl font-extrabold leading-tight tracking-tight">
          The AI + Human operating system<br /> for your healthcare business
        </h1>
        <p className="mt-6 text-lg text-brand-100 max-w-2xl mx-auto">
          Most AI companies sell software. ROSKYRO sells outcomes. You never learn AI, never write a prompt,
          never see a technical process — you approve results and watch your business grow.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
          <Link to="/contact?reason=consultation" className="bg-white text-brand-900 font-semibold px-6 py-3 rounded-xl hover:bg-brand-50">
            Get Free Consultation
          </Link>
          <Link to="/contact?reason=demo" className="border border-white/30 font-semibold px-6 py-3 rounded-xl hover:bg-white/10">
            Book Demo
          </Link>
        </div>

        <div className="mt-14 rounded-2xl border border-white/10 bg-white/5 backdrop-blur px-6 py-10">
          <p className="text-xs uppercase tracking-wide text-brand-200 font-semibold mb-4">Your Dashboard, At A Glance</p>
          <div className="grid sm:grid-cols-3 gap-4 text-left">
            <div className="rounded-xl bg-white/5 border border-white/10 p-4">
              <p className="text-xs text-brand-200">🚀 Grow</p>
              <p className="text-sm font-semibold mt-1">Visibility score, reviews, ranking</p>
            </div>
            <div className="rounded-xl bg-white/5 border border-white/10 p-4">
              <p className="text-xs text-brand-200">⚙️ Manage</p>
              <p className="text-sm font-semibold mt-1">Appointments, queue, billing</p>
            </div>
            <div className="rounded-xl bg-white/5 border border-white/10 p-4">
              <p className="text-xs text-brand-200">🤝 Networking Marketing</p>
              <p className="text-sm font-semibold mt-1">Referrals, partner network</p>
            </div>
          </div>
        </div>
      </section>

      <section className="bg-white text-gray-900 rounded-t-[2.5rem] py-16">
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-lg font-semibold text-gray-500 text-center">Trusted by healthcare businesses like</h2>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {TRUSTED_BY.map((a) => (
              <span key={a} className="text-sm bg-brand-50 text-brand-700 px-3 py-1.5 rounded-full font-medium">{a}</span>
            ))}
          </div>

          <div className="mt-16">
            <h2 className="text-2xl font-bold text-center text-gray-900">Three Core Promises</h2>
            <p className="text-center text-sm text-gray-500 mt-3 max-w-xl mx-auto">
              ROSKYRO is a <span className="font-semibold text-gray-700">Monthly Subscription</span> (annual
              membership available at ~20% off) across three separately-priced pillars — take what you need, or
              bundle all three and save. No long-term contract, cancel any time.
            </p>
            <div className="mt-8 grid md:grid-cols-3 gap-6">
              {PILLARS.map((p) => (
                <div key={p.code} className="border border-gray-200 rounded-2xl p-6">
                  <div className="flex items-center gap-2">
                    <span className="text-xl">{p.emoji}</span>
                    <h3 className="font-bold text-lg text-gray-900">{p.title}</h3>
                  </div>
                  <p className="text-sm text-gray-500 mt-0.5">{p.subtitle}</p>
                  <p className="text-2xl font-extrabold text-gray-900 mt-3">
                    {priceByCode[p.code] != null
                      ? <>₹{Number(priceByCode[p.code]).toLocaleString('en-IN')}<span className="text-sm font-normal text-gray-400">/month</span></>
                      : <span className="text-base font-normal text-gray-400">See pricing →</span>}
                  </p>
                  <ul className="mt-4 space-y-1.5">
                    {p.items.map((i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                        <span className="mt-0.5 text-brand-600">✓</span><span>{i}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="text-xs italic text-gray-400 mt-4">{p.promise}</p>
                </div>
              ))}
            </div>
            <div className="text-center mt-8">
              <Link to="/pricing" className="text-brand-700 font-semibold text-sm">See full pricing & the bundled Complete Platform →</Link>
            </div>
          </div>

          <div className="mt-20">
            <h2 className="text-2xl font-bold text-center text-gray-900">Why ROSKYRO</h2>
            <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {WHY_ROSKYRO.map((w) => (
                <div key={w.title} className="border border-gray-200 rounded-2xl p-6">
                  <div className="h-10 w-10 rounded-xl bg-brand-50 flex items-center justify-center text-lg">{w.emoji}</div>
                  <h3 className="font-bold text-gray-900 mt-3">{w.title}</h3>
                  <p className="text-sm text-gray-600 mt-2 leading-relaxed">{w.body}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-20">
            <h2 className="text-2xl font-bold text-center text-gray-900">How ROSKYRO Works</h2>
            <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
              {HOW_IT_WORKS.map((s) => (
                <div key={s.step} className="text-center">
                  <div className="h-12 w-12 mx-auto rounded-full bg-brand-950 text-white flex items-center justify-center font-bold">{s.step}</div>
                  <h3 className="font-bold text-gray-900 mt-4">{s.title}</h3>
                  <p className="text-sm text-gray-600 mt-1.5 leading-relaxed">{s.body}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="mt-20">
            <h2 className="text-2xl font-bold text-center text-gray-900">Industries We Serve</h2>
            <div className="mt-6 flex flex-wrap justify-center gap-2 max-w-3xl mx-auto">
              {INDUSTRIES.map((a) => (
                <span key={a} className="text-sm bg-gray-50 border border-gray-200 text-gray-700 px-3 py-1.5 rounded-full font-medium">{a}</span>
              ))}
            </div>
          </div>

          <div className="mt-20 border border-gray-200 rounded-2xl p-8 md:p-12">
            <div className="max-w-2xl mx-auto text-center">
              <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-brand-50 text-brand-700 rounded-full px-3 py-1 mb-4">
                {'\u{1F91D}'} Networking Marketing
              </p>
              <h3 className="text-2xl font-bold text-gray-900">Verified Healthcare Service Partners</h3>
              <p className="mt-3 text-gray-600">
                Connect with trusted specialists, diagnostic labs, imaging centers, rehabilitation providers, and home
                healthcare services — all from one platform. Listing your business as a Networking Marketing partner is always
                free — every doctor, clinic and hospital chooses their own partners on their own terms.
              </p>
              <Link to="/register" className="inline-block mt-4 text-brand-700 font-semibold text-sm">Join Networking Marketing for free →</Link>
            </div>
          </div>

          <div className="mt-20">
            <h2 className="text-2xl font-bold text-center text-gray-900">Frequently Asked Questions</h2>
            <div className="mt-8 max-w-3xl mx-auto">
              <FaqList items={FAQ_HOMEPAGE} />
            </div>
            <div className="text-center mt-6">
              <Link to="/faq" className="text-brand-700 font-semibold text-sm">See all FAQs →</Link>
            </div>
          </div>

          <div className="mt-20 bg-brand-950 text-white rounded-2xl p-8 md:p-12 text-center">
            <h3 className="text-2xl font-bold">Ready to Grow Your Healthcare Business?</h3>
            <p className="mt-3 text-brand-100 max-w-2xl mx-auto">
              "How does this reduce work for the healthcare business owner while increasing measurable business
              growth?" Every feature in ROSKYRO Healthcare OS answers that question — or it doesn't ship.
            </p>
            <Link to="/contact?reason=demo" className="inline-block mt-6 bg-white text-brand-900 font-semibold px-6 py-3 rounded-xl hover:bg-brand-50">
              Book Demo
            </Link>
          </div>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
