import { useState } from 'react';
import clsx from 'clsx';

const PILLAR_STYLE = {
  grow: { emoji: '\u{1F680}', ring: 'ring-amber-200', accent: 'text-amber-700', bg: 'bg-amber-50' },
  manage: { emoji: '\u{2699}\u{FE0F}', ring: 'ring-blue-200', accent: 'text-blue-700', bg: 'bg-blue-50' },
  connect: { emoji: '\u{1F91D}', ring: 'ring-teal-200', accent: 'text-teal-700', bg: 'bg-teal-50' },
  complete: { emoji: '\u{2B50}', ring: 'ring-brand-300', accent: 'text-brand-700', bg: 'bg-brand-50' },
};

function formatPrice(p) {
  return new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(Number(p));
}

export default function PricingCards({
  plans,
  activeCodes = [],
  onSelect,
  ctaLabel = 'Get Started',
  busyCode = null,
  showCycleToggle = true,
}) {
  const [cycle, setCycle] = useState('monthly');
  // Add-ons (e.g. "Reel Making") are optional extras, not one of the core
  // pillars/bundle -- they're never part of this grid or the bundle-savings
  // math, and pages that want to offer them render their own separate card
  // (see the `plans` array passed in still contains them, for that purpose).
  const sorted = [...plans].filter((p) => !p.is_addon).sort((a, b) => a.sort_order - b.sort_order);
  const priceField = cycle === 'yearly' ? 'yearly_price' : 'monthly_price';
  const individualTotal = sorted
    .filter((p) => !p.is_bundle)
    .reduce((sum, p) => sum + Number(p[priceField]), 0);
  const bundle = sorted.find((p) => p.is_bundle);
  const savings = bundle ? individualTotal - Number(bundle[priceField]) : 0;

  return (
    <div>
      {/* Every pillar is a recurring subscription — SaaS + Managed Services,
          billed on a cycle the customer picks, cancel any time. */}
      {showCycleToggle && (
        <div className="flex items-center justify-center gap-4 mb-8">
          <span className={clsx('text-sm font-medium', cycle === 'monthly' ? 'text-gray-900' : 'text-gray-400')}>Monthly Subscription</span>
          <button
            type="button"
            role="switch"
            aria-checked={cycle === 'yearly'}
            onClick={() => setCycle((c) => (c === 'monthly' ? 'yearly' : 'monthly'))}
            className={clsx('shrink-0 relative w-11 h-6 rounded-full transition-colors', cycle === 'yearly' ? 'bg-brand-600' : 'bg-gray-300')}
          >
            <span className={clsx('absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform', cycle === 'yearly' ? 'translate-x-5' : 'translate-x-0')} />
          </button>
          <span className={clsx('text-sm font-medium flex items-center gap-2 whitespace-nowrap', cycle === 'yearly' ? 'text-gray-900' : 'text-gray-400')}>
            Annual Membership
            <span className="text-[11px] font-semibold bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">Save 20%</span>
          </span>
        </div>
      )}

      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-5">
        {sorted.map((plan) => {
          const style = PILLAR_STYLE[plan.code] || PILLAR_STYLE.complete;
          const isActive = activeCodes.includes(plan.code);
          const price = plan[priceField];
          return (
            <div
              key={plan.code}
              className={clsx(
                'relative rounded-2xl border bg-white p-6 flex flex-col',
                plan.is_bundle ? 'border-brand-300 ring-2 ring-brand-200 shadow-lg md:scale-[1.03]' : 'border-gray-200'
              )}
            >
              {plan.badge && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 bg-brand-600 text-white text-xs font-semibold px-3 py-1 rounded-full whitespace-nowrap">
                  {plan.badge}{savings > 0 ? ` — Save ${cycle === 'yearly' ? '₹' + formatPrice(savings) + '/yr' : '₹' + formatPrice(savings) + '/mo'}` : ''}
                </span>
              )}
              <div className={clsx('h-10 w-10 rounded-xl flex items-center justify-center text-lg mb-3', style.bg)}>{style.emoji}</div>
              <h3 className="text-lg font-bold text-gray-900">{plan.name}</h3>
              <p className="text-sm text-gray-500 mt-0.5">{plan.tagline}</p>

              <div className="mt-4">
                <span className="text-3xl font-extrabold text-gray-900">{'₹'}{formatPrice(price)}</span>
                <span className="text-sm text-gray-400">/{cycle === 'yearly' ? 'year' : 'month'}</span>
                <p className="text-xs font-semibold text-brand-700 mt-1 uppercase tracking-wide">
                  {cycle === 'yearly' ? 'Annual Membership' : 'Monthly Subscription'}
                </p>
              </div>

              <ul className="mt-5 space-y-2 flex-1">
                {(plan.features || []).map((f) => (
                  <li key={f} className="flex items-start gap-2 text-sm text-gray-600">
                    <span className={clsx('mt-0.5', style.accent)}>{'✓'}</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>

              <p className="text-xs text-gray-400 mt-5">Best for</p>
              <p className="text-sm text-gray-700">{plan.best_for}</p>

              {plan.customer_promise && (
                <p className="text-sm italic text-gray-500 mt-3 border-l-2 border-gray-200 pl-3">"{plan.customer_promise}"</p>
              )}

              {!plan.is_bundle && (
                <p className="text-xs text-gray-400 mt-4 text-center">Cancel Anytime • No Long-Term Contract</p>
              )}

              {onSelect && (
                <button
                  onClick={() => onSelect(plan, cycle)}
                  disabled={isActive || busyCode === plan.code}
                  className={clsx(
                    'mt-4 w-full rounded-lg py-2.5 text-sm font-semibold transition',
                    isActive
                      ? 'bg-emerald-50 text-emerald-700 cursor-default'
                      : plan.is_bundle
                      ? 'bg-brand-600 text-white hover:bg-brand-700'
                      : 'bg-gray-900 text-white hover:bg-gray-800'
                  )}
                >
                  {isActive ? 'Active on your account' : busyCode === plan.code ? 'Activating…' : ctaLabel}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
