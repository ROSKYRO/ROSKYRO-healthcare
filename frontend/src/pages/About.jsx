import { Link } from 'react-router-dom';
import { PublicHeader, PublicFooter } from '../components/PublicNav';

const MISSION_POINTS = [
  { emoji: '\u{1F4C8}', title: 'Get More Patients', body: 'AI-powered visibility and reputation growth that keeps your appointment book full.' },
  { emoji: '\u{1F91D}', title: 'Build Trust', body: 'Verified reviews, transparent pricing and human-reviewed AI so patients trust what they see.' },
  { emoji: '\u{2699}\u{FE0F}', title: 'Simplify Operations', body: 'One platform for appointments, patients, billing and communication — no more juggling five tools.' },
  { emoji: '\u{1F310}', title: 'Connect with Healthcare Network', body: "A verified partner network across India's diagnostics, imaging, rehab and specialist referrals." },
];

const CORE_VALUES = [
  { emoji: '\u{1F512}', title: 'Trust', body: 'We earn trust through transparent pricing, verified partners and honest reporting — no hidden numbers.' },
  { emoji: '\u{1F4A1}', title: 'Innovation', body: "We keep pace with how AI search and patient discovery actually change, so you don't have to track it yourself." },
  { emoji: '\u{1F50D}', title: 'Transparency', body: 'Every AI-touched output is human-reviewed, every payment flow is explained plainly, no black boxes.' },
  { emoji: '\u{1F331}', title: 'Growth', body: 'We measure ourselves by your measurable outcomes — more patients, smoother operations, a stronger network.' },
  { emoji: '\u{2764}\u{FE0F}', title: 'Customer First', body: 'Every feature answers one question: does this reduce work for the business owner and grow their business?' },
];

const WHY_CHOOSE_US = [
  { title: 'Healthcare Focused', body: 'Built only for healthcare businesses, not a generic tool retrofitted for the industry.' },
  { title: 'AI Powered', body: 'AI handles the heavy lifting on visibility, content and day-to-day operations.' },
  { title: 'Managed Services', body: 'A real team executes and reviews — you approve outcomes, not tasks.' },
  { title: 'Affordable Pricing', body: 'Pay only for the pillars you need, with bundle savings across all three.' },
  { title: 'Dedicated Support', body: 'Reachable over WhatsApp and call — not just a support ticket queue.' },
];

const PROCESS = [
  { step: '1', title: 'Discovery', body: 'We learn your business, current visibility, operations and network gaps.' },
  { step: '2', title: 'Planning', body: 'We map which pillars and features fit your business and in what order.' },
  { step: '3', title: 'Implementation', body: 'Your account is set up, staff trained, and pillars switched on.' },
  { step: '4', title: 'Optimization', body: 'We tune visibility, operations and partner connections based on real results.' },
  { step: '5', title: 'Growth', body: 'You track measurable outcomes every month — more patients, less chaos, a stronger network.' },
];

export default function About() {
  return (
    <div className="min-h-screen bg-gray-50">
      <PublicHeader />

      <section className="max-w-3xl mx-auto px-6 pt-8 pb-14 text-center">
        <p className="inline-block text-xs font-semibold tracking-wide uppercase bg-brand-50 text-brand-700 rounded-full px-3 py-1 mb-5">
          About ROSKYRO
        </p>
        <h1 className="text-3xl md:text-4xl font-extrabold text-gray-900 tracking-tight">
          Helping Healthcare Businesses Grow Smarter with AI
        </h1>
        <p className="mt-4 text-gray-500 leading-relaxed">
          Most healthcare business owners didn't get into medicine to become AI operators. ROSKYRO exists so
          they never have to — you run your clinic, hospital, or lab, and we run the AI + Human operating system
          underneath it: getting you more patients, keeping your day-to-day organized, and connecting you to a
          trusted network of healthcare partners.
        </p>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-16">
        <div className="bg-white border border-gray-200 rounded-2xl p-8 md:p-12">
          <h2 className="text-xl font-bold text-gray-900">Our Story</h2>
          <p className="mt-4 text-sm text-gray-600 leading-relaxed">
            ROSKYRO started because we kept seeing the same problem: healthcare businesses — doctors, clinics,
            hospitals, diagnostic labs — are excellent at patient care and consistently underserved by the tools
            meant to help them grow. Marketing agencies sell campaigns without operational context. Software
            vendors sell dashboards without anyone running them. Referral networks stay informal, built on
            personal phone numbers and word of mouth, with no visibility into who sent what to whom.
          </p>
          <p className="mt-3 text-sm text-gray-600 leading-relaxed">
            We built ROSKYRO to close that gap — one platform that combines AI-driven growth, day-to-day
            operations, and a verified partner network, backed by a human team that actually executes the work
            instead of leaving you to figure it out.
          </p>
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-16 grid md:grid-cols-2 gap-6">
        <div className="bg-brand-950 text-white rounded-2xl p-8 md:p-10">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-200">Our Vision</p>
          <h2 className="text-xl font-bold mt-2">Become India's Healthcare Growth Platform</h2>
          <p className="mt-3 text-brand-100 text-sm leading-relaxed">
            We want every healthcare business in India — from a single-doctor clinic to a multi-specialty
            hospital — to have access to the same AI-powered growth and operational tools that were once only
            available to large, well-funded chains.
          </p>
        </div>
        <div className="bg-white border border-gray-200 rounded-2xl p-8 md:p-10">
          <p className="text-xs font-semibold uppercase tracking-wide text-brand-700">Our Mission</p>
          <div className="mt-4 space-y-4">
            {MISSION_POINTS.map((m) => (
              <div key={m.title} className="flex items-start gap-3">
                <span className="text-lg">{m.emoji}</span>
                <div>
                  <p className="text-sm font-semibold text-gray-900">{m.title}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{m.body}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-16">
        <h2 className="text-2xl font-bold text-gray-900 text-center">Our Core Values</h2>
        <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-5 gap-5">
          {CORE_VALUES.map((v) => (
            <div key={v.title} className="bg-white border border-gray-200 rounded-2xl p-5 text-center">
              <div className="h-10 w-10 mx-auto rounded-xl bg-brand-50 flex items-center justify-center text-lg">{v.emoji}</div>
              <h3 className="font-bold text-gray-900 mt-3 text-sm">{v.title}</h3>
              <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">{v.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-16">
        <h2 className="text-2xl font-bold text-gray-900 text-center">Why Choose Us</h2>
        <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-5 gap-5">
          {WHY_CHOOSE_US.map((w) => (
            <div key={w.title} className="border border-gray-200 rounded-2xl p-5 bg-gray-50">
              <h3 className="font-bold text-gray-900 text-sm">{w.title}</h3>
              <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">{w.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 pb-16">
        <h2 className="text-2xl font-bold text-gray-900 text-center">Meet Our Process</h2>
        <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-5 gap-5">
          {PROCESS.map((s) => (
            <div key={s.step} className="text-center">
              <div className="h-12 w-12 mx-auto rounded-full bg-brand-950 text-white flex items-center justify-center font-bold">{s.step}</div>
              <h3 className="font-bold text-gray-900 mt-4 text-sm">{s.title}</h3>
              <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">{s.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-3xl mx-auto px-6 pb-20 text-center">
        <h2 className="text-xl font-bold text-gray-900">Let's Grow Together</h2>
        <p className="text-gray-500 mt-2">Start free, pick only the pillars you need, cancel any time.</p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-4">
          <Link to="/register" className="bg-brand-600 text-white font-semibold px-6 py-3 rounded-xl hover:bg-brand-700">
            Start your free onboarding
          </Link>
          <Link to="/contact" className="border border-gray-300 font-semibold px-6 py-3 rounded-xl text-gray-700 hover:bg-gray-50">
            Talk to us
          </Link>
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
