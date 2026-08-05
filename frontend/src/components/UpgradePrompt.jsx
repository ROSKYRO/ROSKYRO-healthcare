import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../lib/api';
import { Card, Button } from './ui';

// Fixed: price used to be a hardcoded literal per pillar ('14,999' /
// '9,999' / '4,999') baked straight into the bundle. This ONE component is
// reused across every locked-feature page in the app (GrowthHub, Patients,
// Appointments, Billing, Reports, Queue, ...), so a stale price here was
// the single highest-impact instance of the bug: a super admin repricing a
// plan via internal/PricingManagement.jsx (PATCH /plans/{code}) had no way
// to ever reach these pages without a frontend redeploy. Same fix as
// Landing.jsx/Dashboard.jsx: static copy (emoji, name, tagline) stays here,
// price now always comes live from GET /plans, matched by `code`.
const PILLAR_INFO = {
  grow: { emoji: '\u{1F680}', name: 'GROW', tagline: 'AI Visibility, Reviews, SEO, Social Media & Content — all managed for you.' },
  manage: { emoji: '\u{2699}\u{FE0F}', name: 'MANAGE', tagline: 'Patient CRM, Appointments, Queue, Billing & WhatsApp — run your business without the chaos.' },
  connect: { emoji: '\u{1F91D}', name: 'CONNECT', tagline: 'A verified network of trusted healthcare partners, with tracked referrals.' },
};

export default function UpgradePrompt({ pillar }) {
  const info = PILLAR_INFO[pillar] || {};
  const [price, setPrice] = useState(null);

  useEffect(() => {
    // Best-effort only -- same as Landing.jsx: if this fails, the price
    // line below just doesn't render rather than showing a stale/fake
    // number.
    api.get('/plans').then((res) => {
      const plan = (res.data.plans || []).find((p) => p.code === pillar);
      if (plan) setPrice(plan.monthly_price);
    }).catch(() => {});
  }, [pillar]);

  return (
    <Card className="p-10 text-center max-w-lg mx-auto">
      <div className="h-12 w-12 rounded-2xl bg-brand-50 flex items-center justify-center text-2xl mx-auto">{info.emoji}</div>
      <h2 className="text-xl font-bold text-gray-900 mt-4">This is part of ROSKYRO {info.name}</h2>
      <p className="text-sm text-gray-500 mt-2">{info.tagline}</p>
      {price != null && (
        <p className="text-2xl font-extrabold text-gray-900 mt-4">₹{Number(price).toLocaleString('en-IN')}<span className="text-sm font-normal text-gray-400">/month</span></p>
      )}
      <p className="text-xs font-semibold text-brand-700 uppercase tracking-wide mt-1">Monthly Subscription · Cancel Anytime</p>
      <Link to="/app/plans">
        <Button className="mt-5">Activate {info.name}</Button>
      </Link>
    </Card>
  );
}
