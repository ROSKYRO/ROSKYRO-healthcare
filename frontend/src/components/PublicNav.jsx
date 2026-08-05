import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import clsx from 'clsx';
import api from '../lib/api';
import logo from '../assets/logo.png';

const LINKS = [
  { to: '/', label: 'Home' },
  { to: '/services', label: 'Services' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/about', label: 'About Us' },
  { to: '/contact', label: 'Contact Us' },
];

/** Shared header for every public marketing page so nav + sign-in/get-started
 * stays consistent site-wide. Every public page (including the homepage,
 * which is a plain white page like the rest) renders the header on a light
 * background -- `landing` only swaps the accent color from the site-wide
 * green ('brand') to the logo-matched indigo-violet ('landing'), scoped to
 * the homepage only. */
export function PublicHeader({ landing }) {
  const { pathname } = useLocation();
  return (
    <header className="max-w-6xl mx-auto px-6 py-6 flex items-center justify-between">
      <Link to="/" className={clsx('flex items-center gap-2 text-xl font-extrabold tracking-tight', landing ? 'text-landing-900' : 'text-brand-700')}>
        <img src={logo} alt="ROSKYRO" className="h-9 w-9 object-contain" />
        ROSKYRO
      </Link>
      <nav className="hidden md:flex items-center gap-6">
        {LINKS.map((l) => {
          const isActive = pathname === l.to;
          return (
            <Link
              key={l.to}
              to={l.to}
              className={clsx(
                'text-sm font-medium transition',
                isActive
                  ? (landing ? 'text-landing-700' : 'text-brand-700')
                  : 'text-gray-600 hover:text-gray-900'
              )}
            >
              {l.label}
            </Link>
          );
        })}
      </nav>
      <div className="flex items-center gap-3">
        <Link to="/login" className="text-sm font-medium text-gray-600 hover:text-gray-900">
          Sign in
        </Link>
        <Link
          to="/register"
          className={clsx(
            'text-sm font-semibold px-4 py-2 rounded-lg transition text-white',
            landing ? 'bg-landing-600 hover:bg-landing-700' : 'bg-brand-600 hover:bg-brand-700'
          )}
        >
          Get started
        </Link>
      </div>
    </header>
  );
}

const FOOTER_COMPANY = [
  { to: '/', label: 'Home' },
  { to: '/about', label: 'About Us' },
  { to: '/services', label: 'Services' },
  { to: '/pricing', label: 'Pricing' },
  { to: '/contact', label: 'Contact Us' },
  { to: '/faq', label: 'FAQ' },
];

const FOOTER_SOLUTIONS = [
  { to: '/services', label: 'Grow' },
  { to: '/services', label: 'Manage' },
  { to: '/services', label: 'Networking Marketing' },
  { to: '/services', label: 'AI Visibility' },
  { to: '/services', label: 'Google Business Profile' },
  { to: '/services', label: 'Review Growth' },
  { to: '/services', label: 'CRM' },
  { to: '/services', label: 'Appointment Management' },
  { to: '/services', label: 'Referral Network' },
];

const FOOTER_INDUSTRIES = [
  'Doctors', 'Clinics', 'Hospitals', 'Diagnostic Labs', 'Imaging Centers',
  'Dental Clinics', 'Physiotherapy', 'Rehabilitation Centers', 'Veterinary Clinics',
];

const FOOTER_LEGAL = [
  { to: '/privacy-policy', label: 'Privacy Policy' },
  { to: '/terms-conditions', label: 'Terms & Conditions' },
  { to: '/refund-policy', label: 'Refund Policy' },
  { to: '/cookie-policy', label: 'Cookie Policy' },
  { to: '/disclaimer', label: 'Disclaimer' },
];

// Real ROSKYRO profile URLs, supplied by the user. X/Twitter is still a
// placeholder ("#") -- no handle was provided for it yet.
const WHATSAPP_NUMBER = '919244166752'; // +91 92441 66752, wa.me format (no +/spaces)

const SOCIAL_LINKS = [
  { label: 'Facebook', href: 'https://www.facebook.com/roskyro.in' },
  { label: 'Instagram', href: 'https://www.instagram.com/roskyro.in/' },
  { label: 'LinkedIn', href: 'https://www.linkedin.com/company/roskyro.in/' },
  { label: 'X / Twitter', href: '#' },
  { label: 'YouTube', href: 'https://www.youtube.com/@ROSKYRO' },
  { label: 'WhatsApp', href: `https://wa.me/${WHATSAPP_NUMBER}` },
  { label: 'Google Business Profile', href: 'https://www.google.com/search?q=ROSKYRO&stick=H4sIAAAAAAAA_-NgU1I1qDAxMUlOMk40tjRMMrRISrG0MqgwT01OMzFOM080TE02MDNIXsTKHuQf7B0Z5A8ARqHqGDMAAAA&hl=en&mat=CVdRfy7VAYb3ElcBa0lj_9FwjFs37r9uTaXAm4RVEJm-jFB87T_N2s6SWpsJ0b-qWRIXdPl9SlI82NPI9_xElTYzWor5N7fPDpEDxCL0NIIYgt5foMccsfGwTTLXbtqpOVU&authuser=0' },
];

function FooterColumn({ title, children }) {
  return (
    <div>
      <p className="text-xs font-semibold text-white uppercase tracking-wide mb-4">{title}</p>
      {children}
    </div>
  );
}

function NewsletterBox() {
  const [email, setEmail] = useState('');
  const [state, setState] = useState('idle'); // idle | busy | done | error

  async function submit(e) {
    e.preventDefault();
    if (!email.trim()) return;
    setState('busy');
    try {
      await api.post('/public/newsletter-subscribe', { email: email.trim() });
      setState('done');
    } catch {
      setState('error');
    }
  }

  if (state === 'done') {
    return <p className="text-sm text-brand-200 mt-3">Thanks — you're subscribed!</p>;
  }

  return (
    <form onSubmit={submit} className="mt-3">
      <div className="flex gap-2">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@business.com"
          className="min-w-0 flex-1 rounded-lg bg-white/10 border border-white/10 px-3 py-2 text-sm text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
        <button
          type="submit"
          disabled={state === 'busy'}
          className="shrink-0 bg-brand-600 hover:bg-brand-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition disabled:opacity-60"
        >
          Subscribe
        </button>
      </div>
      {state === 'error' && <p className="text-sm text-rose-300 mt-2">Could not subscribe right now. Please try again.</p>}
    </form>
  );
}

/** Full sitemap-style footer used on every public marketing page. The
 * WhatsApp number and social profile links are real (supplied by the
 * user); the email/office-address/hours are still placeholders -- swap
 * those for the real business details before going live. */
export function PublicFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="bg-gray-950 text-gray-400">
      <div className="max-w-6xl mx-auto px-6 pt-16 pb-10">
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-10">
          <div className="lg:col-span-1">
            <Link to="/" className="flex items-center gap-2 text-xl font-extrabold tracking-tight text-white">
              <img src={logo} alt="ROSKYRO" className="h-9 w-9 object-contain" />
              ROSKYRO
            </Link>
            <p className="text-sm mt-3 leading-relaxed">
              The AI + Human operating system for healthcare businesses — get more patients, run your day-to-day, and
              connect with a trusted partner network.
            </p>
          </div>

          <FooterColumn title="Company">
            <ul className="space-y-2.5">
              {FOOTER_COMPANY.map((l) => (
                <li key={l.label}><Link to={l.to} className="text-sm hover:text-white transition">{l.label}</Link></li>
              ))}
            </ul>
          </FooterColumn>

          <FooterColumn title="Solutions">
            <ul className="space-y-2.5">
              {FOOTER_SOLUTIONS.map((l) => (
                <li key={l.label}><Link to={l.to} className="text-sm hover:text-white transition">{l.label}</Link></li>
              ))}
            </ul>
          </FooterColumn>

          <FooterColumn title="Industries">
            <ul className="space-y-2.5">
              {FOOTER_INDUSTRIES.map((i) => (
                <li key={i} className="text-sm">{i}</li>
              ))}
            </ul>
          </FooterColumn>

          <div>
            <FooterColumn title="Contact">
              <ul className="space-y-2.5 text-sm">
                <li>+91 92441 66752</li>
                <li>roskyroofficial@gmail.com</li>
                <li>www.roskyro.com</li>
                <li>Chhattisgarh, India</li>
                <li>Mon–Sat, 9:00 AM – 7:00 PM IST</li>
              </ul>
            </FooterColumn>

            <p className="text-xs font-semibold text-white uppercase tracking-wide mt-6 mb-3">Follow us</p>
            <div className="flex flex-wrap gap-3">
              {SOCIAL_LINKS.map((s) => (
                <a
                  key={s.label}
                  href={s.href}
                  target={s.href === '#' ? undefined : '_blank'}
                  rel={s.href === '#' ? undefined : 'noreferrer'}
                  aria-label={s.label}
                  className="text-xs bg-white/5 hover:bg-white/10 text-gray-300 px-2.5 py-1.5 rounded-md transition"
                >
                  {s.label}
                </a>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-12 border-t border-white/10 pt-8 grid sm:grid-cols-2 gap-6 items-start">
          <div>
            <p className="text-sm font-semibold text-white">Stay updated</p>
            <p className="text-sm mt-1">Get healthcare growth tips, product updates & offers.</p>
            <NewsletterBox />
          </div>
          <div className="sm:text-right">
            <Link to="/contact" className="inline-block bg-white text-gray-950 text-sm font-semibold px-5 py-2.5 rounded-lg hover:bg-gray-100 transition">
              Book a Free Demo
            </Link>
          </div>
        </div>
      </div>

      <div className="border-t border-white/10">
        <div className="max-w-6xl mx-auto px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
          <p>© {year} ROSKYRO. All Rights Reserved. · Made with ❤️ in India.</p>
          <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1">
            {FOOTER_LEGAL.map((l, i) => (
              <span key={l.label} className="flex items-center gap-4">
                <Link to={l.to} className="hover:text-white transition">{l.label}</Link>
                {i < FOOTER_LEGAL.length - 1 && <span className="text-gray-700">|</span>}
              </span>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
}
