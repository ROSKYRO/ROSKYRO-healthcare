import { Link } from 'react-router-dom';
import { Card, Button } from './ui';

const PILLAR_INFO = {
  grow: { emoji: '\u{1F680}', name: 'GROW', price: '14,999', tagline: 'AI Visibility, Reviews, SEO, Social Media & Content — all managed for you.' },
  manage: { emoji: '\u{2699}\u{FE0F}', name: 'MANAGE', price: '9,999', tagline: 'Patient CRM, Appointments, Queue, Billing & WhatsApp — run your business without the chaos.' },
  connect: { emoji: '\u{1F91D}', name: 'CONNECT', price: '4,999', tagline: 'A verified network of trusted healthcare partners, with tracked referrals.' },
};

export default function UpgradePrompt({ pillar }) {
  const info = PILLAR_INFO[pillar] || {};
  return (
    <Card className="p-10 text-center max-w-lg mx-auto">
      <div className="h-12 w-12 rounded-2xl bg-brand-50 flex items-center justify-center text-2xl mx-auto">{info.emoji}</div>
      <h2 className="text-xl font-bold text-gray-900 mt-4">This is part of ROSKYRO {info.name}</h2>
      <p className="text-sm text-gray-500 mt-2">{info.tagline}</p>
      <p className="text-2xl font-extrabold text-gray-900 mt-4">₹{info.price}<span className="text-sm font-normal text-gray-400">/month</span></p>
      <p className="text-xs font-semibold text-brand-700 uppercase tracking-wide mt-1">Monthly Subscription · Cancel Anytime</p>
      <Link to="/app/plans">
        <Button className="mt-5">Activate {info.name}</Button>
      </Link>
    </Card>
  );
}
